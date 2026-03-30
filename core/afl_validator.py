
"""
AFL Validator - Comprehensive sanity checker for AmiBroker Formula Language
Improved version based on official documentation and common mistake patterns.
"""

import re
from typing import Dict, List, Set, Tuple, Any
from dataclasses import dataclass, field

# =============================================================================
# VALID AMIBROKER COLORS (UPDATED WITH color.txt AND SYNTAX FILES)
# =============================================================================

VALID_COLORS: Set[str] = {
    # Custom palette colors (Explicitly allowed per color.txt)
    "colorCustom1", "colorCustom2", "colorCustom3", "colorCustom4",
    "colorCustom5", "colorCustom6", "colorCustom7", "colorCustom8",
    "colorCustom9", "colorCustom10", "colorCustom11", "colorCustom12",
    "colorCustom13", "colorCustom14", "colorCustom15", "colorCustom16",

    # Standard colors (indices 16-55)
    "colorBlack", "colorBrown", "colorDarkOliveGreen", "colorDarkGreen",
    "colorDarkTeal", "colorDarkBlue", "colorIndigo", "colorDarkGrey",
    "colorDarkRed", "colorOrange", "colorDarkYellow", "colorGreen",
    "colorTeal", "colorBlue", "colorBlueGrey", "colorGrey40", # colorGrey40 added
    "colorRed", "colorLightOrange", "colorLime", "colorSeaGreen",
    "colorAqua", "colorLightBlue", "colorViolet", "colorGrey50",
    "colorPink", "colorGold", "colorYellow", "colorBrightGreen",
    "colorTurquoise", "colorSkyblue", "colorPlum", "colorLightGrey",
    "colorRose", "colorTan", "colorLightYellow", "colorPaleGreen",
    "colorPaleTurquoise", "colorPaleBlue", "colorLavender", "colorWhite",
    
    # Additional standard constants
    "colorDefault", "colorGrey", # colorGrey is distinct from Grey40/50
}

# =============================================================================
# VALID AMIBROKER FUNCTIONS (UPDATED BASED ON SYNTAX.TXT)
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
    # "UltOsc": 1, # REMOVED - Common hallucination. UltOsc requires 3 cycles.
    "RMI": 1,     # Added from SYNTAX.txt
    "Trix": 1,    # Added from SYNTAX.txt
    "OBV": 1,     # Also acts as no-arg depending on version, but usually 1 or 0. 
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
    "Ref": 2,
    "LinearReg": 2,
    "LinRegSlope": 2,
    "LinRegIntercept": 2,
    "TSF": 2,
    "Correlation": 3,
    "Percentile": 3,
    "PercentRank": 2,
    "OscP": 2, # Oscillator Price
    "OscV": 2, # Oscillator Volume
}

# Multi-argument functions
MULTI_ARG_FUNCTIONS: Dict[str, Tuple[int, int]] = {  # (min_args, max_args)
    "Cum": (1, 1),
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
    "AddMultiTextColumn": (3, 7), # Updated based on Code Requirements
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
    "UltOsc": (3, 3), # Fixed: Requires 3 cycles
}

# No argument functions
NO_ARG_FUNCTIONS: Set[str] = {
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
# VALID PLOT STYLES & SHAPES (From SYNTAX.txt)
# =============================================================================

VALID_PLOT_STYLES: Set[str] = {
    "styleLine", "styleHistogram", "styleCandle", "styleBar", "styleArea",
    "styleDots", "styleThick", "styleDashed", "styleNoLine", "styleOwnScale",
    "styleNoLabel", "styleNoRescale", "styleLeftAxisScale", "styleNoDraw",
    "styleNoTitle", "stylePointAndFigure", "styleCloud", "styleClipMinMax",
    "styleGradient", "styleStaircase", "styleSwingDots", "styleLog",
}

VALID_SHAPES: Set[str] = {
    "shapeNone", "shapeUpArrow", "shapeDownArrow", "shapeUpTriangle",
    "shapeDownTriangle", "shapeHollowUpArrow", "shapeHollowDownArrow",
    "shapeHollowUpTriangle", "shapeHollowDownTriangle", "shapeCircle",
    "shapeHollowCircle", "shapeSquare", "shapeHollowSquare", "shapeStar",
    "shapeHollowStar", "shapeDigit0", "shapeDigit1", "shapeDigit2",
    "shapeDigit3", "shapeDigit4", "shapeDigit5", "shapeDigit6", "shapeDigit7",
    "shapeDigit8", "shapeDigit9", "shapeSmallCircle", "shapeSmallSquare",
    "shapeSmallUpTriangle", "shapeSmallDownTriangle", "shapePositionAbove",
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
            "total_issues": len(self.errors) + len(self.color_issues) + 
                           len(self.function_issues) + len(self.reserved_word_issues)
        }


# =============================================================================
# AFL VALIDATOR CLASS
# =============================================================================

class AFLValidator:
    def __init__(self):
        self.all_functions = {
            **{k: v for k, v in SINGLE_ARG_FUNCTIONS.items()},
            **{k: v for k, v in DOUBLE_ARG_FUNCTIONS.items()},
            **{k: v[0] for k, v in MULTI_ARG_FUNCTIONS.items()}, 
            **{k: 0 for k in NO_ARG_FUNCTIONS},
        }

    def validate(self, code: str) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        clean_code = self._remove_comments(code)

        self._validate_colors(clean_code, result)
        self._validate_functions(clean_code, result)
        self._validate_reserved_words(clean_code, result)
        self._validate_plot_styles(clean_code, result)
        self._validate_shapes(clean_code, result)
        self._validate_syntax(code, result) # Pass original code to catch syntax structure
        self._validate_common_mistakes(clean_code, result) # New checks

        result.is_valid = (
            len(result.errors) == 0 and
            len(result.color_issues) == 0 and
            len(result.function_issues) == 0
        )
        return result

    def _remove_comments(self, code: str) -> str:
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        return code

    def _validate_colors(self, code: str, result: ValidationResult):
        """Validate that only official AmiBroker colors are used."""
        
        # 1. Find all potential color constants (camelCase starting with color)
        color_pattern = r'\b(color[A-Za-z0-9_]*?)\b'
        found_colors = re.findall(color_pattern, code)

        # 2. Check for ColorRGB usage and valid variable assignment
        colorrgb_vars: set = set()
        colorrgb_assign_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*ColorRGB\s*\('
        for m in re.finditer(colorrgb_assign_pattern, code):
            var_name = m.group(1)
            # If user assigns ColorRGB to a reserved color name (e.g. colorRed = ColorRGB(...))
            if var_name in VALID_COLORS:
                result.color_issues.append(
                    f"CRITICAL: Variable '{var_name}' shadows a predefined AmiBroker color constant. "
                    f"Use a unique name like 'MyColor' instead."
                )
            else:
                colorrgb_vars.add(var_name)

        # 3. Validate found constants
        for color in found_colors:
            # Skip if it was a variable assigned via ColorRGB (e.g. MyColor = ColorRGB(..))
            if color in colorrgb_vars:
                continue
            
            if color not in VALID_COLORS:
                suggestions = self._find_similar(color, VALID_COLORS)
                msg = f"Invalid color constant '{color}'. "
                if suggestions:
                    msg += f"Did you mean: {', '.join(suggestions)}?"
                else:
                    msg += "Use official colors or define custom color via ColorRGB()."
                result.color_issues.append(msg)

    def _validate_functions(self, code: str, result: ValidationResult):
        func_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)'
        
        for match in re.finditer(func_pattern, code):
            func_name = match.group(1)
            args_str = match.group(2).strip()
            arg_count = self._count_args(args_str) if args_str else 0
            
            # Skip if it looks like a function call but is actually a keyword (if, while)
            if func_name in ["if", "while", "for", "else"]:
                continue

            # Check single-argument functions
            if func_name in SINGLE_ARG_FUNCTIONS:
                expected = SINGLE_ARG_FUNCTIONS[func_name]
                if arg_count != expected:
                    # Detect RSI(Close, 14) hallucination
                    if arg_count == 2 and expected == 1:
                        result.function_issues.append(
                            f"HALLUCINATION DETECTED: {func_name}({args_str}) - "
                            f"{func_name} takes {expected} argument (period only), NOT an array. "
                            f"Correct usage: {func_name}(14)"
                        )
                    else:
                        result.function_issues.append(
                            f"Invalid {func_name}() call. Expected {expected} arg, got {arg_count}."
                        )
            
            # Check double-argument functions
            elif func_name in DOUBLE_ARG_FUNCTIONS:
                expected = DOUBLE_ARG_FUNCTIONS[func_name]
                if arg_count != expected:
                    if arg_count == 1 and expected == 2:
                        result.function_issues.append(
                            f"MISSING ARRAY: {func_name}({args_str}) - "
                            f"{func_name} requires an array (e.g., Close) AND period. "
                            f"Correct usage: {func_name}(Close, {args_str})"
                        )
                    else:
                        result.function_issues.append(
                            f"Invalid {func_name}() call. Expected {expected} args, got {arg_count}."
                        )
            
            # Check multi-argument functions
            elif func_name in MULTI_ARG_FUNCTIONS:
                min_args, max_args = MULTI_ARG_FUNCTIONS[func_name]
                if not (min_args <= arg_count <= max_args):
                    result.function_issues.append(
                        f"Invalid {func_name}() call. Expected {min_args}-{max_args} args, got {arg_count}."
                    )
            
            # Check no-arg functions
            elif func_name in NO_ARG_FUNCTIONS:
                if arg_count > 0 and func_name not in ["Status"]:
                    result.function_issues.append(
                        f"Invalid {func_name}() call with {arg_count} arguments. "
                        f"{func_name} takes no arguments."
                    )
            
            # Check for IIf Hallucinations (Assignment inside IIf)
            if func_name == "IIf":
                # Look for '=' inside arguments, which implies assignment, not value return
                # Pattern: IIf( cond, var = 1, var = 2 ) -> WRONG
                if re.search(r'=\s*(?:[^,]+)\s*,', args_str) or re.search(r',\s*[^,=]+=\s*', args_str):
                     result.function_issues.append(
                         f"SYNTAX ERROR: Assignment detected inside IIf() arguments. "
                         f"IIf returns a value, it does not perform assignment. "
                         f"Use: result = IIf(condition, true_val, false_val);"
                     )

    def _validate_common_mistakes(self, code: str, result: ValidationResult):
        """
        Checks for common logical mistakes found in AMIRBROKER MISTAKES.txt
        """
        
        # 1. Array in scalar 'if' statement
        # Matches: if ( Close > Open ) or if ( Cross(MA, Close) )
        # Does NOT match: if ( Close[i] > Open[i] ) or if ( var > 0 )
        # Heuristic: if keyword is followed by standard array names without subscripts
        if_pattern = r'\bif\s*\(([^)]+)\)'
        for m in re.finditer(if_pattern, code):
            condition = m.group(1)
            # Check if condition contains un-subscripted array names
            # This regex looks for array names NOT followed by [
            if re.search(r'\b(Close|Open|High|Low|Volume|C|O|H|L|V)\b(?!\s*\[)', condition):
                result.warnings.append(
                    f"SCALAR IF ERROR: 'if' statement contains array condition '{condition.strip()}'. "
                    f"'if' statements require a single True/False value, not an array. "
                    f"Use IIf() for array logic, or loop with subscripts [i]."
                )

        # 2. TimeFrameSet without TimeFrameExpand
        if re.search(r'\bTimeFrameSet\s*\(', code):
            if not re.search(r'\bTimeFrameExpand\s*\(', code):
                result.errors.append(
                    "LOGIC ERROR: TimeFrameSet() used without corresponding TimeFrameExpand(). "
                    "Data compressed to a different timeframe must be expanded back to original "
                    "interval to align with other data arrays."
                )
        
        # 3. Assignment in condition (= vs ==)
        # Matches: if ( x = 5 ) -> Wrong. Should be ==
        # Allow common patterns like variable initialization outside logic blocks
        assign_in_if = re.search(r'\bif\s*\([^)]*[^=!<>]=[^=][^)]*\)', code)
        if assign_in_if:
            result.warnings.append(
                f"ASSIGNMENT IN CONDITION: '{assign_in_if.group(0)}'. "
                f"Did you mean to use '==' (equality check) instead of '=' (assignment)?"
            )

    def _count_args(self, args_str: str) -> int:
        if not args_str.strip(): return 0
        count = 1; depth = 0
        for char in args_str:
            if char == '(': depth += 1
            elif char == ')': depth -= 1
            elif char == ',' and depth == 0: count += 1
        return count
    
    def _validate_reserved_words(self, code: str, result: ValidationResult):
        assignment_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*='
        
        for match in re.finditer(assignment_pattern, code):
            var_name = match.group(1)
            
            if var_name in RESERVED_PRICE_ARRAYS:
                result.reserved_word_issues.append(
                    f"Reserved word '{var_name}' used as variable. This shadows the built-in price array."
                )
            
            if var_name in self.all_functions or var_name in NO_ARG_FUNCTIONS:
                result.reserved_word_issues.append(
                    f"Function name '{var_name}' used as variable. This shadows the built-in function."
                )
    
    def _validate_plot_styles(self, code: str, result: ValidationResult):
        style_pattern = r'\bstyle[A-Za-z0-9_]*'
        found_styles = re.findall(style_pattern, code)
        for style in found_styles:
            if style not in VALID_PLOT_STYLES:
                suggestions = self._find_similar(style, VALID_PLOT_STYLES)
                if suggestions:
                    result.style_issues.append(f"Invalid style '{style}'. Did you mean: {', '.join(suggestions)}?")
    
    def _validate_shapes(self, code: str, result: ValidationResult):
        shape_pattern = r'\bshape[A-Za-z0-9_]*'
        found_shapes = re.findall(shape_pattern, code)
        for shape in found_shapes:
            if shape not in VALID_SHAPES:
                suggestions = self._find_similar(shape, VALID_SHAPES)
                if suggestions:
                    result.style_issues.append(f"Invalid shape '{shape}'. Did you mean: {', '.join(suggestions)}?")

    def _validate_syntax(self, code: str, result: ValidationResult):
        lines = code.split("\n")
        paren = bracket = brace = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//"): continue
            if "//" in line: line = line[:line.index("//")]
            
            for char in line:
                if char == '(': paren += 1
                elif char == ')': paren -= 1
                elif char == '[': bracket += 1
                elif char == ']': bracket -= 1
                elif char == '{': brace += 1
                elif char == '}': brace -= 1
        
        if paren != 0: result.errors.append(f"Unbalanced parentheses: {abs(paren)} {'open' if paren > 0 else 'close'} missing")
        if bracket != 0: result.errors.append(f"Unbalanced brackets: {abs(bracket)} {'open' if bracket > 0 else 'close'} missing")
        if brace != 0: result.errors.append(f"Unbalanced braces: {abs(brace)} {'open' if brace > 0 else 'close'} missing")

    def _find_similar(self, word: str, valid_set: Set[str], max_results: int = 3) -> List[str]:
        word_lower = word.lower()
        suggestions = []
        for valid in valid_set:
            valid_lower = valid.lower()
            if valid_lower.startswith(word_lower[:4]) or word_lower in valid_lower:
                suggestions.append(valid)
        return suggestions[:max_results]
    
    def fix_code(self, code: str) -> Tuple[str, List[str]]:
        fixes = []
        fixed_code = code
        
        # Fix: Single-arg function hallucinations (RSI(Close, 14) -> RSI(14))
        for func in SINGLE_ARG_FUNCTIONS:
            pattern = rf'\b{func}\s*\(\s*(Close|Open|High|Low|Volume|C|O|H|L|V)\s*,\s*(\d+)\s*\)'
            if re.search(pattern, fixed_code, re.IGNORECASE):
                fixed_code = re.sub(pattern, rf'{func}(\2)', fixed_code, flags=re.IGNORECASE)
                fixes.append(f"Fixed {func}(Close, n) -> {func}(n)")
        
        # Fix: Double-arg function hallucinations (MA(14) -> MA(Close, 14))
        for func in ["MA", "EMA", "SMA", "WMA", "DEMA", "TEMA"]:
            pattern = rf'\b{func}\s*\(\s*(\d+)\s*\)'
            if re.search(pattern, fixed_code):
                fixed_code = re.sub(pattern, rf'{func}(Close, \1)', fixed_code)
                fixes.append(f"Fixed {func}(n) -> {func}(Close, n)")
        
        return fixed_code, fixes

# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_afl_code(code: str) -> Dict[str, Any]:
    validator = AFLValidator()
    result = validator.validate(code)
    return result.to_dict()

def fix_afl_code(code: str) -> Dict[str, Any]:
    validator = AFLValidator()
    fixed_code, fixes = validator.fix_code(code)
    validation = validator.validate(fixed_code)
    return {
        "original_code": code,
        "fixed_code": fixed_code,
        "fixes_applied": fixes,
        "validation": validation.to_dict(),
        "is_now_valid": validation.is_valid
    }

def get_valid_colors() -> List[str]: return sorted(list(VALID_COLORS))
def get_valid_styles() -> List[str]: return sorted(list(VALID_PLOT_STYLES))
def get_valid_shapes() -> List[str]: return sorted(list(VALID_SHAPES))
