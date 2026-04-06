import logging
import re

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Token types
_TK_NUMBER = 'NUMBER'
_TK_ROW_REF = 'ROW_REF'
_TK_PLUS = '+'
_TK_MINUS = '-'
_TK_STAR = '*'
_TK_SLASH = '/'
_TK_LPAREN = '('
_TK_RPAREN = ')'
_TK_EOF = 'EOF'

# Tokenizer pattern
_TOKEN_RE = re.compile(
    r'\s*(?:'
    r'(?P<number>[0-9]+(?:\.[0-9]*)?)'          # float or int literal
    r'|(?P<row_ref>row:[\w\.\-]+)'              # row:name reference
    r'|(?P<op>[+\-*/()])'                        # operator or paren
    r')'
)


class SetDBFormulaEngine(models.AbstractModel):
    _name = 'setdb.formula.engine'
    _description = 'SetDB Formula Engine (safe recursive-descent parser)'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def evaluate_formula(self, formula_text, row_values):
        """Parse and evaluate a formula expression.

        Args:
            formula_text: str — formula like "row:przychody - row:koszty"
            row_values: dict — {"przychody": 15000, "koszty": 8000, ...}
                Keys are matched case-insensitively.

        Returns:
            float — the computed result

        Raises:
            UserError on syntax errors or undefined references.
        """
        if not formula_text or not formula_text.strip():
            return 0.0

        # Normalize row_values keys to lowercase
        normalized = {k.lower(): v for k, v in row_values.items()}

        tokens = self._tokenize(formula_text)
        result, pos = self._parse_expr(tokens, 0, normalized)

        if pos < len(tokens) and tokens[pos][0] != _TK_EOF:
            raise UserError(
                "Formula parse error: unexpected token '%s' at position %d."
                % (tokens[pos][1], pos)
            )

        return result

    # ------------------------------------------------------------------
    # Tokenizer
    # ------------------------------------------------------------------

    @api.model
    def _tokenize(self, text):
        """Tokenize formula text into a list of (type, value) tuples.

        Supported tokens:
        - NUMBER: float literals (e.g. 3.14, 100)
        - ROW_REF: row:name references (e.g. row:przychody)
        - Operators: +, -, *, /
        - Parentheses: (, )

        Returns:
            list of (token_type, raw_value) tuples, ending with (EOF, '')
        """
        tokens = []
        pos = 0
        while pos < len(text):
            # Skip whitespace
            if text[pos].isspace():
                pos += 1
                continue

            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise UserError(
                    "Formula tokenization error: unexpected character '%s' at position %d."
                    % (text[pos], pos)
                )

            if m.group('number') is not None:
                tokens.append((_TK_NUMBER, m.group('number')))
            elif m.group('row_ref') is not None:
                tokens.append((_TK_ROW_REF, m.group('row_ref')))
            elif m.group('op') is not None:
                op = m.group('op')
                tk_map = {
                    '+': _TK_PLUS, '-': _TK_MINUS,
                    '*': _TK_STAR, '/': _TK_SLASH,
                    '(': _TK_LPAREN, ')': _TK_RPAREN,
                }
                tokens.append((tk_map[op], op))

            pos = m.end()

        tokens.append((_TK_EOF, ''))
        return tokens

    # ------------------------------------------------------------------
    # Recursive descent parser
    # ------------------------------------------------------------------
    # Grammar:
    #   expr   = term (('+' | '-') term)*
    #   term   = factor (('*' | '/') factor)*
    #   factor = NUMBER | ROW_REF | '(' expr ')' | ('-' factor)

    @api.model
    def _parse_expr(self, tokens, pos, row_values):
        """Parse additive expression: term (('+' | '-') term)*

        Returns:
            (float_value, new_pos)
        """
        left, pos = self._parse_term(tokens, pos, row_values)

        while pos < len(tokens):
            tk_type = tokens[pos][0]
            if tk_type == _TK_PLUS:
                right, pos = self._parse_term(tokens, pos + 1, row_values)
                left = left + right
            elif tk_type == _TK_MINUS:
                right, pos = self._parse_term(tokens, pos + 1, row_values)
                left = left - right
            else:
                break

        return left, pos

    @api.model
    def _parse_term(self, tokens, pos, row_values):
        """Parse multiplicative expression: factor (('*' | '/') factor)*

        Returns:
            (float_value, new_pos)
        """
        left, pos = self._parse_factor(tokens, pos, row_values)

        while pos < len(tokens):
            tk_type = tokens[pos][0]
            if tk_type == _TK_STAR:
                right, pos = self._parse_factor(tokens, pos + 1, row_values)
                left = left * right
            elif tk_type == _TK_SLASH:
                right, pos = self._parse_factor(tokens, pos + 1, row_values)
                if right == 0.0:
                    _logger.warning("Division by zero in formula; returning 0.")
                    left = 0.0
                else:
                    left = left / right
            else:
                break

        return left, pos

    @api.model
    def _parse_factor(self, tokens, pos, row_values):
        """Parse atomic expression: NUMBER | ROW_REF | '(' expr ')' | unary minus.

        Returns:
            (float_value, new_pos)
        """
        if pos >= len(tokens):
            raise UserError("Formula parse error: unexpected end of expression.")

        tk_type, tk_val = tokens[pos]

        # Unary minus
        if tk_type == _TK_MINUS:
            value, pos = self._parse_factor(tokens, pos + 1, row_values)
            return -value, pos

        # Unary plus (just skip it)
        if tk_type == _TK_PLUS:
            return self._parse_factor(tokens, pos + 1, row_values)

        # Number literal
        if tk_type == _TK_NUMBER:
            return float(tk_val), pos + 1

        # Row reference: "row:name"
        if tk_type == _TK_ROW_REF:
            ref_name = tk_val.split(':', 1)[1].lower()
            if ref_name not in row_values:
                raise UserError(
                    "Formula error: undefined reference 'row:%s'. "
                    "Available: %s" % (ref_name, ', '.join(sorted(row_values.keys())))
                )
            val = row_values[ref_name]
            try:
                return float(val), pos + 1
            except (TypeError, ValueError):
                raise UserError(
                    "Formula error: 'row:%s' value '%s' is not numeric." % (ref_name, val)
                )

        # Parenthesized sub-expression
        if tk_type == _TK_LPAREN:
            value, pos = self._parse_expr(tokens, pos + 1, row_values)
            if pos >= len(tokens) or tokens[pos][0] != _TK_RPAREN:
                raise UserError("Formula parse error: missing closing parenthesis.")
            return value, pos + 1

        raise UserError(
            "Formula parse error: unexpected token '%s' at position %d." % (tk_val, pos)
        )
