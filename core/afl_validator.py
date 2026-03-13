"""
AFL Validator - Comprehensive sanity checker for AmiBroker Formula Language
Prevents hallucinations, validates colors, functions, and syntax
"""

import re
from typing import Dict, List, Set, Tuple, Any
from dataclasses import dataclass, field


# =============================================================================
# VALID AMIBROKER COLORS (OFFICIAL ONLY - NO CUSTOM RGB)
# =============================================================================

VALID_COLORS: Set[str] = {
    # Standard colors
    "colorBlack",
    "colorBlue", 
    "colorBrightGreen",
    "colorBrown",
    "colorDarkBlue",
    "colorDarkGreen",
    "colorDarkGrey",
    "colorDarkOliveGreen",
    "colorDarkRed",
    "colorDarkTeal",
    "colorDarkYellow",
    "colorDefault",
    "colorGold",
    "colorGreen",
    "colorGrey40",
    "colorGrey50",
    "colorIndigo",
    "colorLavender",
    "colorLightBlue",
    "colorLightGrey",
    "colorLightOrange",
    "colorLightYellow",
    "colorLime",
    "colorOrange",
    "colorPaleGreen",
    "colorPink",
    "colorPlum",
    "colorRed",
    "colorRose",
    "colorSeaGreen",
    "colorSkyblue",
    "colorTan",
    "colorTeal",
    "colorTurquoise",
    "colorViolet",
    "colorWhite",
    "colorYellow",
    "colorAqua",
}

# Colors that can be used with IIf for conditional coloring
VALID_COLOR_FUNCTIONS = {
    "ParamColor",
    "ColorHSB",
    "ColorRGB",  # Only when using predefined values
    "ColorBlend",
}

# =============================================================================
# VALID AMIBROKER FUNCTIONS
# =============================================================================

# Single argument functions (take ONLY period, NOT array)
SINGLE_ARG_FUNCTIONS: Dict[str, int] = {
    "RSI": 1,
    "ATR": 1,
    "ADX": 1,
    "CCI": 1,
    "MFI": 1,
    "PDI": 1,
    "MDI": 1,
    "StochK": 1,
    "StochD": 1,
    "Chaikin": 1,
    "UltOsc": 1,  # Has defaults
}

# Double argument functions (take array AND period)
DOUBLE_ARG_FUNCTIONS: Dict[str, int] = {
    "MA": 2,
    "EMA": 2,
    "SMA": 2,
    "WMA": 2,
    "DEMA": 2,
    "TEMA": 2,
    "AMA": 2,
    "KAMA": 2,
    "T3": 2,
    "Wilders": 2,
    "ROC": 2,
    "Momentum": 2,
    "HHV": 2,
    "LLV": 2,
    "HHVBars": 2,
    "LLVBars": 2,
    "StDev": 2,
    "Sum": 2,
    "Cum": 1,  # Special - takes 1 arg (array)
    "Ref": 2,
    "LinearReg": 2,
    "LinRegSlope": 2,
    "LinRegIntercept": 2,
    "TSF": 2,
    "Correlation": 3,
    "Percentile": 3,
    "PercentRank": 2,
}

# Multi-argument functions
MULTI_ARG_FUNCTIONS: Dict[str, Tuple[int, int]] = {  # (min_args, max_args)
    "BBandTop": (3, 3),
    "BBandBot": (3, 3),
    "MACD": (0, 2),
    "Signal": (0, 3),
    "SAR": (0, 2),
    "ApplyStop": (3, 6),
    "Param": (4, 5),
    "ParamToggle": (3, 3),
    "ParamList": (3, 3),
    "ParamStr": (3, 3),
    "ParamColor": (2, 2),
    "Optimize": (5, 5),
    "Plot": (3, 8),
    "PlotShapes": (3, 5),
    "PlotOHLC": (5, 9),
    "PlotGrid": (1, 2),
    "PlotText": (4, 5),
    "AddColumn": (2, 5),
    "AddTextColumn": (2, 4),
    "IIf": (3, 3),
    "Cross": (2, 2),
    "ExRem": (2, 2),
    "Flip": (2, 2),
    "BarsSince": (1, 1),
    "ValueWhen": (2, 3),
    "HighestSince": (2, 3),
    "LowestSince": (2, 3),
    "SumSince": (2, 3),
    "Peak": (2, 3),
    "Trough": (2, 3),
    "PeakBars": (2, 3),
    "TroughBars": (2, 3),
    "Foreign": (2, 3),
    "SetForeign": (1, 3),
    "SetTradeDelays": (4, 4),
    "SetOption": (2, 2),
}

# No argument functions
NO_ARG_FUNCTIONS: Set[str] = {
    "OBV",
    "GetCursorMouseButtons",
    "GetCursorXPosition",
    "GetCursorYPosition",
    "Name",
    "FullName",
    "Now",
    "DateTime",
    "DateNum",
    "TimeNum",
    "Day",
    "Month",
    "Year",
    "Hour",
    "Minute",
    "Second",
    "DayOfWeek",
    "DayOfYear",
    "BarIndex",
    "BarCount",
    "Status",
    "RestorePriceArrays",
    "GetChartID",
}

# =============================================================================
# VALID PLOT STYLES
# =============================================================================

VALID_PLOT_STYLES: Set[str] = {
    "styleLine",
    "styleHistogram", 
    "styleCandle",
    "styleBar",
    "styleArea",
    "styleDots",
    "styleThick",
    "styleDashed",
    "styleNoLine",
    "styleOwnScale",
    "styleNoLabel",
    "styleNoRescale",
    "styleLeftAxisScale",
    "styleNoDraw",
    "styleNoTitle",
    "stylePointAndFigure",
    "styleCloud",
    "styleClipMinMax",
    "styleGradient",
    "styleStaircase",
    "styleSwingDots",
}

# =============================================================================
# VALID SHAPES
# =============================================================================

VALID_SHAPES: Set[str] = {
    "shapeNone",
    "shapeUpArrow",
    "shapeDownArrow",
    "shapeUpTriangle",
    "shapeDownTriangle",
    "shapeHollowUpArrow",
    "shapeHollowDownArrow",
    "shapeHollowUpTriangle",
    "shapeHollowDownTriangle",
    "shapeCircle",
    "shapeHollowCircle",
    "shapeSquare",
    "shapeHollowSquare",
    "shapeStar",
    "shapeHollowStar",
    "shapeDigit0", "shapeDigit1", "shapeDigit2", "shapeDigit3", "shapeDigit4",
    "shapeDigit5", "shapeDigit6", "shapeDigit7", "shapeDigit8", "shapeDigit9",
    "shapeSmallCircle",
    "shapeSmallSquare",
    "shapeSmallUpTriangle",
    "shapeSmallDownTriangle",
}

# =============================================================================
# RESERVED WORDS
# =============================================================================

RESERVED_PRICE_ARRAYS: Set[str] = {
    "Open", "High", "Low", "Close", "Volume", "OpenInt",
    "O", "H", "L", "C", "V", "OI", "Average", "A",
}

RESERVED_TRADING: Set[str] = {
    "Buy", "Sell", "Short", "Cover",
    "BuyPrice", "SellPrice", "ShortPrice", "CoverPrice",
}

RESERVED_SYSTEM: Set[str] = {
    "Filter", "PositionSize", "PositionScore",
    "NumColumns", "MaxGraph", "title",
    "True", "False", "Null",
}

ALL_RESERVED: Set[str] = RESERVED_PRICE_ARRAYS | RESERVED_TRADING | RESERVED_SYSTEM


# =============================================================================
# VALIDATION RESULT
# =============================================================================

@dataclass
class ValidationResult:
    """Result of AFL validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    color_issues: List[str] = field(default_factory=list)
    function_issues: List[str] = field(default_factory=list)
    reserved_word_issues: List[str] = field(default_factory=list)
    style_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "color_issues": self.color_issues,
            "function_issues": self.function_issues,
            "reserved_word_issues": self.reserved_word_issues,
            "style_issues": self.style_issues,
            "suggestions": self.suggestions,
            "total_issues": len(self.errors) + len(self.color_issues) + len(self.function_issues) + len(self.reserved_word_issues)
        }


# =============================================================================
# AFL VALIDATOR CLASS
# =============================================================================

class AFLValidator:
    """
    Comprehensive AFL code validator.
    Prevents hallucinations by validating:
    - Colors (only official AmiBroker colors)
    - Function signatures (correct argument counts)
    - Reserved words (not used as variables)
    - Plot styles and shapes
    """
    
    def __init__(self):
        self.all_functions = {
            **{k: v for k, v in SINGLE_ARG_FUNCTIONS.items()},
            **{k: v for k, v in DOUBLE_ARG_FUNCTIONS.items()},
        }
    
    def validate(self, code: str) -> ValidationResult:
        """
        Perform comprehensive validation of AFL code.
        """
        result = ValidationResult(is_valid=True)
        
        # Remove comments for analysis
        clean_code = self._remove_comments(code)
        
        # Run all validations
        self._validate_colors(clean_code, result)
        self._validate_functions(clean_code, result)
        self._validate_reserved_words(clean_code, result)
        self._validate_plot_styles(clean_code, result)
        self._validate_shapes(clean_code, result)
        self._validate_syntax(code, result)
        
        # Determine overall validity
        result.is_valid = (
            len(result.errors) == 0 and 
            len(result.color_issues) == 0 and
            len(result.function_issues) == 0
        )
        
        return result
    
    def _remove_comments(self, code: str) -> str:
        """Remove single-line and multi-line comments."""
        # Remove multi-line comments /* */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # Remove single-line comments //
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        return code
    
    def _validate_colors(self, code: str, result: ValidationResult):
        """
        Validate that only official AmiBroker colors are used.
        No custom RGB values allowed.
        """
        # Find all color references (words starting with 'color')
        color_pattern = r'\bcolor[A-Za-z0-9_]*'
        found_colors = re.findall(color_pattern, code, re.IGNORECASE)
        
        for color in found_colors:
            # Check if it's a valid color constant
            if color not in VALID_COLORS:
                # Check if it's close to a valid color (typo)
                suggestions = self._find_similar(color, VALID_COLORS)
                if suggestions:
                    result.color_issues.append(
                        f"Invalid color '{color}'. Did you mean: {', '.join(suggestions)}?"
                    )
                else:
                    result.color_issues.append(
                        f"Invalid color '{color}'. Use only official AmiBroker colors like colorRed, colorGreen, colorBlue, etc."
                    )
        
        # Check for custom RGB usage (not allowed except in specific functions)
        rgb_pattern = r'\bRGB\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)'
        rgb_matches = re.findall(rgb_pattern, code)
        
        for rgb in rgb_matches:
            # Check if RGB is inside ColorRGB function (allowed)
            if f"ColorRGB{rgb}" not in code.replace(" ", ""):
                result.color_issues.append(
                    f"Custom RGB color '{rgb}' detected. Use predefined colors like colorRed, colorGreen instead."
                )
                result.suggestions.append(
                    "Replace custom RGB with: colorRed, colorGreen, colorBlue, colorYellow, colorOrange, colorWhite, colorBlack"
                )
        
        # Check for ColorHSB usage (discouraged)
        hsb_pattern = r'\bColorHSB\s*\('
        if re.search(hsb_pattern, code):
            result.warnings.append(
                "ColorHSB detected. Consider using predefined colors for consistency."
            )
    
    def _validate_functions(self, code: str, result: ValidationResult):
        """
        Validate function signatures and argument counts.
        Catches common hallucinations like RSI(Close, 14) instead of RSI(14).
        """
        # Pattern to match function calls: FunctionName(args)
        func_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)'
        
        for match in re.finditer(func_pattern, code):
            func_name = match.group(1)
            args_str = match.group(2).strip()
            
            # Count arguments (simple comma split, accounting for nested parentheses)
            arg_count = self._count_args(args_str) if args_str else 0
            
            # Check single-argument functions (common hallucination: adding Close as first arg)
            if func_name in SINGLE_ARG_FUNCTIONS:
                expected = SINGLE_ARG_FUNCTIONS[func_name]
                if arg_count != expected:
                    if arg_count == 2:
                        # Common mistake: RSI(Close, 14) instead of RSI(14)
                        result.function_issues.append(
                            f"HALLUCINATION DETECTED: {func_name}({args_str}) - "
                            f"{func_name} takes {expected} argument (period only), NOT an array. "
                            f"Correct usage: {func_name}(14)"
                        )
                    else:
                        result.function_issues.append(
                            f"Invalid {func_name}() call with {arg_count} arguments. Expected {expected}."
                        )
            
            # Check double-argument functions (common hallucination: missing array)
            elif func_name in DOUBLE_ARG_FUNCTIONS:
                expected = DOUBLE_ARG_FUNCTIONS[func_name]
                if arg_count != expected:
                    if arg_count == 1 and expected == 2:
                        # Common mistake: MA(14) instead of MA(Close, 14)
                        result.function_issues.append(
                            f"HALLUCINATION DETECTED: {func_name}({args_str}) - "
                            f"{func_name} requires {expected} arguments (array, period). "
                            f"Correct usage: {func_name}(Close, {args_str})"
                        )
                    else:
                        result.function_issues.append(
                            f"Invalid {func_name}() call with {arg_count} arguments. Expected {expected}."
                        )
            
            # Check multi-argument functions
            elif func_name in MULTI_ARG_FUNCTIONS:
                min_args, max_args = MULTI_ARG_FUNCTIONS[func_name]
                if arg_count < min_args or arg_count > max_args:
                    result.function_issues.append(
                        f"Invalid {func_name}() call with {arg_count} arguments. "
                        f"Expected {min_args}-{max_args} arguments."
                    )
            
            # Check no-arg functions
            elif func_name in NO_ARG_FUNCTIONS:
                if arg_count > 0 and func_name not in ["Status"]:  # Status can take args
                    result.function_issues.append(
                        f"Invalid {func_name}() call with {arg_count} arguments. "
                        f"{func_name} takes no arguments."
                    )
    
    def _count_args(self, args_str: str) -> int:
        """Count arguments, accounting for nested parentheses."""
        if not args_str.strip():
            return 0
        
        count = 1
        depth = 0
        for char in args_str:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                count += 1
        
        return count
    
    def _validate_reserved_words(self, code: str, result: ValidationResult):
        """
        Check for reserved words being used as variable names.
        """
        # Pattern: variable = something (assignment)
        assignment_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*='
        
        for match in re.finditer(assignment_pattern, code):
            var_name = match.group(1)
            
            # Check if using price array as custom variable (shadowing)
            if var_name in RESERVED_PRICE_ARRAYS:
                result.reserved_word_issues.append(
                    f"Reserved word '{var_name}' used as variable. This shadows the built-in price array. "
                    f"Use '{var_name}_Val' or '{var_name}_Custom' instead."
                )
            
            # Check if using function name as variable (very common mistake)
            if var_name in self.all_functions or var_name in NO_ARG_FUNCTIONS:
                result.reserved_word_issues.append(
                    f"Function name '{var_name}' used as variable. This shadows the built-in function. "
                    f"Use '{var_name}_Val' or '{var_name}_Value' instead."
                )
    
    def _validate_plot_styles(self, code: str, result: ValidationResult):
        """
        Validate that only official plot styles are used.
        """
        # Find all style references
        style_pattern = r'\bstyle[A-Za-z0-9_]*'
        found_styles = re.findall(style_pattern, code)
        
        for style in found_styles:
            if style not in VALID_PLOT_STYLES:
                suggestions = self._find_similar(style, VALID_PLOT_STYLES)
                if suggestions:
                    result.style_issues.append(
                        f"Invalid plot style '{style}'. Did you mean: {', '.join(suggestions)}?"
                    )
                else:
                    result.style_issues.append(
                        f"Invalid plot style '{style}'. Use official styles like styleLine, styleHistogram, etc."
                    )
    
    def _validate_shapes(self, code: str, result: ValidationResult):
        """
        Validate that only official shapes are used.
        """
        shape_pattern = r'\bshape[A-Za-z0-9_]*'
        found_shapes = re.findall(shape_pattern, code)
        
        for shape in found_shapes:
            if shape not in VALID_SHAPES:
                suggestions = self._find_similar(shape, VALID_SHAPES)
                if suggestions:
                    result.style_issues.append(
                        f"Invalid shape '{shape}'. Did you mean: {', '.join(suggestions)}?"
                    )
                else:
                    result.style_issues.append(
                        f"Invalid shape '{shape}'. Use official shapes like shapeUpArrow, shapeDownArrow, etc."
                    )
    
    def _validate_syntax(self, code: str, result: ValidationResult):
        """
        Basic syntax validation.
        """
        lines = code.split("\n")
        
        # Check balanced parentheses/brackets/braces
        paren = bracket = brace = 0
        for i, line in enumerate(lines, 1):
            # Skip full-line comments
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            
            # Remove inline comments
            if "//" in line:
                line = line[:line.index("//")]
            
            for char in line:
                if char == '(': paren += 1
                elif char == ')': paren -= 1
                elif char == '[': bracket += 1
                elif char == ']': bracket -= 1
                elif char == '{': brace += 1
                elif char == '}': brace -= 1
        
        if paren != 0:
            result.errors.append(f"Unbalanced parentheses: {abs(paren)} {'open' if paren > 0 else 'close'} missing")
        if bracket != 0:
            result.errors.append(f"Unbalanced brackets: {abs(bracket)} {'open' if bracket > 0 else 'close'} missing")
        if brace != 0:
            result.errors.append(f"Unbalanced braces: {abs(brace)} {'open' if brace > 0 else 'close'} missing")
        
        # Check for common syntax issues
        if re.search(r';\s*;', code):
            result.warnings.append("Double semicolons detected (;;)")
        
        # Check for missing semicolons in common patterns
        # (This is a heuristic - AFL is forgiving about semicolons)
        
    def _find_similar(self, word: str, valid_set: Set[str], max_results: int = 3) -> List[str]:
        """
        Find similar words from valid set (for typo suggestions).
        """
        word_lower = word.lower()
        suggestions = []
        
        for valid in valid_set:
            valid_lower = valid.lower()
            # Simple similarity: starts with same prefix or contains word
            if valid_lower.startswith(word_lower[:4]) or word_lower in valid_lower:
                suggestions.append(valid)
        
        return suggestions[:max_results]
    
    def fix_code(self, code: str) -> Tuple[str, List[str]]:
        """
        Attempt to automatically fix common issues in AFL code.
        Returns (fixed_code, list_of_fixes_applied).
        """
        fixes = []
        fixed_code = code
        
        # Fix 1: Single-arg function hallucinations (RSI(Close, 14) -> RSI(14))
        for func in SINGLE_ARG_FUNCTIONS:
            pattern = rf'\b{func}\s*\(\s*(Close|Open|High|Low|Volume|C|O|H|L|V)\s*,\s*(\d+)\s*\)'
            if re.search(pattern, fixed_code, re.IGNORECASE):
                fixed_code = re.sub(pattern, rf'{func}(\2)', fixed_code, flags=re.IGNORECASE)
                fixes.append(f"Fixed {func}(Close, n) -> {func}(n)")
        
        # Fix 2: Double-arg function hallucinations (MA(14) -> MA(Close, 14))
        for func in ["MA", "EMA", "SMA", "WMA", "DEMA", "TEMA"]:
            pattern = rf'\b{func}\s*\(\s*(\d+)\s*\)'
            if re.search(pattern, fixed_code):
                fixed_code = re.sub(pattern, rf'{func}(Close, \1)', fixed_code)
                fixes.append(f"Fixed {func}(n) -> {func}(Close, n)")
        
        # Fix 3: Variable shadowing (RSI = RSI(14) -> RSI_Val = RSI(14))
        for func in list(SINGLE_ARG_FUNCTIONS.keys()) + list(DOUBLE_ARG_FUNCTIONS.keys()):
            pattern = rf'\b{func}\s*=\s*{func}\s*\('
            if re.search(pattern, fixed_code):
                fixed_code = re.sub(pattern, f'{func}_Val = {func}(', fixed_code)
                fixes.append(f"Fixed variable shadowing: {func} -> {func}_Val")
        
        return fixed_code, fixes


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_afl_code(code: str) -> Dict[str, Any]:
    """
    Convenience function to validate AFL code.
    Returns a dictionary with validation results.
    """
    validator = AFLValidator()
    result = validator.validate(code)
    return result.to_dict()


def fix_afl_code(code: str) -> Dict[str, Any]:
    """
    Attempt to fix common AFL issues.
    Returns dictionary with fixed code and list of fixes applied.
    """
    validator = AFLValidator()
    fixed_code, fixes = validator.fix_code(code)
    
    # Validate the fixed code
    validation = validator.validate(fixed_code)
    
    return {
        "original_code": code,
        "fixed_code": fixed_code,
        "fixes_applied": fixes,
        "validation": validation.to_dict(),
        "is_now_valid": validation.is_valid
    }


def get_valid_colors() -> List[str]:
    """Return list of all valid AmiBroker colors."""
    return sorted(list(VALID_COLORS))


def get_valid_styles() -> List[str]:
    """Return list of all valid plot styles."""
    return sorted(list(VALID_PLOT_STYLES))


def get_valid_shapes() -> List[str]:
    """Return list of all valid shapes."""
    return sorted(list(VALID_SHAPES))