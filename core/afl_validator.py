#!/usr/bin/env python3
"""
AFL Syntax Checker & Validator - ULTIMATE COMPREHENSIVE ENGINE
================================================================
Covers EVERY error/warning from AmirbrokerErrors.txt (Errors 1-54, 90-94, 701-706, Warnings 501-503)
+ AFL_VALIDATION_RULES.md + SKILL_AMIBROKER_AFL.md + amibroker_llm_guide.md
+ 03_common-mistakes.md + afl_function_reference.md + afl SYNTAX.txt

This validator detects:
- All 68 documented AmiBroker errors/warnings
- Cascading errors (errors that trigger other errors)
- Type mismatches, subscript errors, loop errors
- Function signature violations
- Color/style/shape constant errors
- Backtest configuration errors
- Multi-timeframe errors
- Optimization errors
- OLE/COM warnings
- And much more...

NO GUI - Pure validation engine for API/integration use.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple, Optional, Any
from enum import Enum


# ====================== ENUMERATIONS ======================
class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    SUGGESTION = "SUGGESTION"

class ErrorCategory(Enum):
    SYNTAX = "Syntax"
    TYPE = "Type"
    OPERATOR = "Operator"
    FUNCTION = "Function"
    ARGUMENT = "Argument"
    ARRAY = "Array"
    SUBSCRIPT = "Subscript"
    LOOP = "Loop"
    VARIABLE = "Variable"
    CONDITIONAL = "Conditional"
    COLOR = "Color"
    STYLE = "Style"
    SHAPE = "Shape"
    BACKTEST = "Backtest"
    OPTIMIZATION = "Optimization"
    TIMEFRAME = "TimeFrame"
    ROTATIONAL = "Rotational"
    FILE_IO = "File I/O"
    OLE_COM = "OLE/COM"
    STRING = "String"
    MATRIX = "Matrix"
    SIGNAL = "Signal"
    BRACKET = "Bracket"
    IIF = "IIf"
    PLOT = "Plot"
    PARAM = "Param"
    SHADOW = "Shadow"
    CASCADING = "Cascading"
    RESERVED = "Reserved"
    GENERAL = "General"

@dataclass
class Issue:
    line: int
    column: int
    severity: Severity
    category: str
    message: str
    error_code: str = ""
    suggestion: str = ""
    cascading: bool = False
    cascading_parent: int = -1
    cascade_chain: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "error_code": self.error_code,
            "suggestion": self.suggestion,
            "cascading": self.cascading,
            "cascading_parent": self.cascading_parent,
        }

@dataclass
class ValidationResult:
    """Structured result of AFL validation."""
    is_valid: bool
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    suggestion_count: int = 0
    cascade_count: int = 0
    issues: List[Issue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "suggestion_count": self.suggestion_count,
            "cascade_count": self.cascade_count,
            "total_issues": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }

    def get_errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def get_warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def get_cascading(self) -> List[Issue]:
        return [i for i in self.issues if i.cascading]


# ====================== ERROR CODE DATABASE ======================
ERROR_CODES: Dict[int, Dict] = {
    1: {"title": "Operation not allowed. Operator/operand type mismatch",
        "desc": "Arithmetic/string/logical/comparison operator used with invalid data type",
        "fix": "Ensure operands are compatible types (e.g., don't multiply strings)"},
    2: {"title": "Incorrect argument type for math function",
        "desc": "Single-argument math function called with wrong type (e.g., string)",
        "fix": "Pass number or array, not string: sin(x) not sin(\"test\")"},
    3: {"title": "Unary minus requires number or array",
        "desc": "Cannot apply unary minus to strings",
        "fix": "Don't negate strings: -\"test\" is invalid"},
    4: {"title": "Expecting number (not array) in function parameter",
        "desc": "ApplyStop type/mode/ExitAtStop/Volatile must be scalar, not array",
        "fix": "Use scalar values: ApplyStop(stopTypeLoss, stopModePercent, 5)"},
    5: {"title": "Argument has incorrect type",
        "desc": "Function expects different type than provided",
        "fix": "Check function signature: MA(array, period) not MA(string, period)"},
    6: {"title": "IF/WHILE/FOR condition must be numeric (not array)",
        "desc": "if/while/for cannot use array conditions - arrays have multiple values",
        "fix": "Use IIf() for arrays: Buy = IIf(Close>Open, 1, 0); or for loop with [i]"},
    7: {"title": "IF/WHILE/FOR condition cannot be string",
        "desc": "Cannot use string as condition in if/while/for",
        "fix": "Use comparison: if(\"text\" != \"other\") not if(\"text\")"},
    8: {"title": "Cannot assign array to single array element",
        "desc": "Array element can only hold single value, not entire array",
        "fix": "Use indexing: test[i] = Close[i] not test[i] = Close"},
    9: {"title": "Array subscript must be number",
        "desc": "Only numbers accepted as array subscripts, not strings or arrays",
        "fix": "table[1] = 10; not table[\"text\"] = 10;"},
    10: {"title": "Subscript out of range",
         "desc": "Accessing array element below 0 or above BarCount-1",
         "fix": "Always check: if(bar > 0) a[bar] = C[bar-1];"},
    11: {"title": "Subscript operator [] cannot be used on strings",
         "desc": "Cannot index into string variables",
         "fix": "Use StrMid() for string character access"},
    12: {"title": "Subscript [] requires array or number type",
         "desc": "Cannot use subscript on unsupported types like COM objects",
         "fix": "Use array or number variables with []"},
    13: {"title": "Endless loop in WHILE",
         "desc": "while loop never terminates (counter not incremented)",
         "fix": "Ensure loop variable changes: while(i < 5) { x = i; i++; }"},
    14: {"title": "Endless loop in DO-WHILE",
         "desc": "do-while loop never terminates",
         "fix": "Ensure loop variable changes in do-while body"},
    15: {"title": "Endless loop in FOR",
         "desc": "for loop never terminates (increment forgotten)",
         "fix": "Check increment: for(i=0; i<N; i++) not for(i=0; i<N; i)"},
    16: {"title": "Too many arguments",
         "desc": "More arguments passed than function accepts",
         "fix": "Check function signature: MACD(12,26) not MACD(12,26,3)"},
    17: {"title": "Missing arguments",
         "desc": "Fewer arguments passed than required",
         "fix": "Check function signature: Plot(C, \"Name\", color) needs 3+ args"},
    18: {"title": "COM object not initialized or invalid type",
         "desc": "Variable used as COM object but not properly initialized",
         "fix": "Use CreateObject() to initialize COM objects"},
    19: {"title": "COM method/function call failed",
         "desc": "OLE exception during COM method call (wrong/missing args)",
         "fix": "Check COM method arguments and object state"},
    20: {"title": "COM method/function does not exist",
         "desc": "Calling non-existent OLE method/property",
         "fix": "Check available methods: AB.Import() not AB.Test()"},
    21: {"title": "Relative strength base symbol not found",
         "desc": "RelStrength() called with non-existing symbol",
         "fix": "Use valid ticker: RelStrength(\"$SPX\") not RelStrength(\"NonExist\")"},
    22: {"title": "Format argument must be number (not array)",
         "desc": "AddColumn format parameter must be scalar number",
         "fix": "AddColumn(C, \"Close\", 1.2) not AddColumn(C, \"Close\", IIf(...))"},
    23: {"title": "GetExtraData call failed",
         "desc": "GetExtraData() failed - field not supported by plugin",
         "fix": "Use valid field name supported by your data plugin"},
    24: {"title": "Formula requires higher AmiBroker version",
         "desc": "Formula uses features not available in current version",
         "fix": "Upgrade AmiBroker or remove version-specific features"},
    25: {"title": "SetVariable identifier conflict",
         "desc": "Plugin tried to SetVariable with name already in use",
         "fix": "Use different identifier name"},
    26: {"title": "Invalid file handle (zero)",
         "desc": "File I/O function called with null/invalid file handle",
         "fix": "Always check: if(fh) { fputs(...); fclose(fh); }"},
    27: {"title": "Invalid number of arguments in Call Function",
         "desc": "Plugin called internal function with wrong arg count",
         "fix": "Internal plugin error - check plugin code"},
    28: {"title": "Out of memory",
         "desc": "Memory overflow during formula parsing",
         "fix": "Reduce formula complexity or increase system memory"},
    29: {"title": "Variable used without initialization",
         "desc": "Reading variable that was never assigned a value",
         "fix": "Initialize before use: y = 0; z = x + y;"},
    30: {"title": "Syntax error",
         "desc": "General syntax error (unbalanced parens, unrecognized chars, etc.)",
         "fix": "Check for missing closing brackets, typos, invalid operators"},
    31: {"title": "Syntax error - expecting specific token",
         "desc": "Parser expects specific token but finds something else",
         "fix": "while(i < 5) not while i < 5 (need parentheses)"},
    32: {"title": "Syntax error - probably missing semicolon",
         "desc": "Missing semicolon at end of previous statement",
         "fix": "Add semicolon: a = 5; b = 4;"},
    33: {"title": "Identifier already in use (function name conflict)",
         "desc": "Cannot assign to identifier already used for function",
         "fix": "Use return statement: function Test(x) { return 2*x; }"},
    34: {"title": "Identifier already in use (variable name conflict)",
         "desc": "Cannot define function with name of existing variable",
         "fix": "Use different name: Test = 5; function MyTest(x) {...}"},
    35: {"title": "Shift+BREAK pressed - loop terminated",
         "desc": "User manually stopped execution",
         "fix": "User action - no code fix needed"},
    36: {"title": "Function argument has no value",
         "desc": "N-th argument of function call is empty/undefined",
         "fix": "Ensure all arguments have values"},
    37: {"title": "Unsupported field in SetOptions",
         "desc": "Wrong/unsupported option name in SetOption()",
         "fix": "Use valid option: SetOption(\"MaxOpenPositions\", 10)"},
    38: {"title": "Unsupported field in GetOptions",
         "desc": "Wrong/unsupported option name in GetOption()",
         "fix": "Use valid option: GetOption(\"InitialEquity\")"},
    39: {"title": "Cannot set sector - use industry",
         "desc": "CategoryAddSymbol cannot use categorySector",
         "fix": "Use categoryIndustry instead of categorySector"},
    40: {"title": "Cannot remove from sector - use industry",
         "desc": "CategoryRemoveSymbol cannot use categorySector",
         "fix": "Use categoryIndustry instead of categorySector"},
    41: {"title": "Unsupported field in GetRTData",
         "desc": "Invalid field name in GetRTData() call",
         "fix": "Use valid RT data fields only"},
    42: {"title": "#include file not found",
         "desc": "Specified include file does not exist",
         "fix": "Check file path: #include \"valid\\\\path\\\\file.afl\""},
    43: {"title": "Variable stops not supported in Rotational/Raw mode",
         "desc": "Cannot use variable stop amount in rotational trading",
         "fix": "Use fixed stop values in rotational mode"},
    44: {"title": "SectorID() outside 0..63 range",
         "desc": "Data plugin set sector ID incorrectly",
         "fix": "Check data plugin sector ID configuration"},
    45: {"title": "Failed to launch trading interface",
         "desc": "Required trading interface not installed/registered",
         "fix": "Install/register the required trading interface"},
    46: {"title": "Missing comma in function parameters",
         "desc": "Missing comma between function formal parameters",
         "fix": "function MyFun(x, y) not function MyFun(x y)"},
    47: {"title": "Exception during AFL execution",
         "desc": "Unhandled system exception (memory, file handle, etc.)",
         "fix": "Check for invalid handles, memory issues"},
    48: {"title": "N-volume bar compression too small",
         "desc": "TimeFrame N-volume compression produces data longer than base",
         "fix": "Use higher time frame or different compression"},
    49: {"title": "Optimize parameter name must not be empty",
         "desc": "Optimize() called with empty name string",
         "fix": "Optimize(\"Period\", 10, 5, 20, 1) not Optimize(\"\", 10, 5, 20, 1)"},
    50: {"title": "Optimize min must be <= max, step > 0",
         "desc": "Optimize() called with invalid min/max/step values",
         "fix": "Optimize(\"P\", 10, 5, 20, 1) - min<=max, step>0"},
    51: {"title": "Array subscript has Null value",
         "desc": "Using Null as array subscript index",
         "fix": "Ensure subscript is not Null before indexing"},
    52: {"title": "Invalid argument value for function",
         "desc": "Negative value passed where positive expected",
         "fix": "Sum(Close, 15) not Sum(Close, -15)"},
    53: {"title": "Open files not closed",
         "desc": "fopen() called without matching fclose()",
         "fix": "Always fclose(fh) after fopen()"},
    54: {"title": "Incorrect escape sequence",
         "desc": "Invalid \\\\ escape in string (only \\\\n \\\\r \\\\t \\\\\\\\ \\\\\\\" supported)",
         "fix": "Use \\\\\\\\ for backslash: \"C:\\\\\\\\windows\\\\\\\\file.txt\""},
    90: {"title": "Optimizer engine not found",
         "desc": "OptimizerSetEngine called with non-existing engine",
         "fix": "Use valid engine: OptimizerSetEngine(\"trib\")"},
    91: {"title": "OptimizerSetOption expects STRING",
         "desc": "Wrong type passed to OptimizerSetOption",
         "fix": "Pass string for string options"},
    92: {"title": "OptimizerSetOption expects NUMBER",
         "desc": "Wrong type passed to OptimizerSetOption",
         "fix": "Pass number for numeric options"},
    93: {"title": "Unsupported optimizer option",
         "desc": "OptimizerSetOption called with invalid option name",
         "fix": "Use valid option names for the optimizer engine"},
    94: {"title": "External optimizer not selected",
         "desc": "Must call OptimizerSetEngine before OptimizerSetOption",
         "fix": "OptimizerSetEngine(\"trib\"); then OptimizerSetOption(...);"},
    701: {"title": "Missing Buy/Sell assignments",
          "desc": "Backtest formula lacks Buy and/or Sell variable assignments",
          "fix": "Add: Buy = ...; Sell = ...;"},
    702: {"title": "Missing Short/Cover assignments",
          "desc": "Backtest formula lacks Short and/or Cover variable assignments",
          "fix": "Add: Short = ...; Cover = ...; or select Long-only in settings"},
    703: {"title": "Rotational trading requires PositionScore",
          "desc": "EnableRotationalTrading() used without PositionScore",
          "fix": "Add: PositionScore = 50 - RSI();"},
    704: {"title": "Cannot use Buy/Sell in Rotational mode",
          "desc": "Rotational mode uses PositionScore, not Buy/Sell signals",
          "fix": "Remove Buy/Sell or remove EnableRotationalTrading()"},
    705: {"title": "HoldMinBars conflicts with AllowSameBarExit",
          "desc": "Cannot mix HoldMinBars with AllowSameBarExit",
          "fix": "Use one or the other, not both"},
    706: {"title": "Show Arrows needs Trade list",
          "desc": "Cannot show arrows without Trade list report mode",
          "fix": "Set Report mode to Trade list in Settings"},
    501: {"title": "Assignment within conditional",
          "desc": "Using = inside if/while/for (probably meant ==)",
          "fix": "Use == for comparison: if(x == 5) not if(x = 5)"},
    502: {"title": "Too many Plot() calls",
          "desc": "Plot()/PlotOHLC() called over 500 times - highly inefficient",
          "fix": "Combine LineArrays and use single Plot() call"},
    503: {"title": "Using OLE/CreateObject is slow",
          "desc": "OLE calls are slow in multi-threaded applications",
          "fix": "Replace OLE with native AFL commands"},
}

WARNING_CODES = {501, 502, 503}


# ====================== COMPLETE COLOR DATABASE ======================
# ====================== COMPLETE COLOR DATABASE ======================
VALID_COLORS: Set[str] = {
    "colorCustom1", "colorCustom2", "colorCustom3", "colorCustom4",
    "colorCustom5", "colorCustom6", "colorCustom7", "colorCustom8",
    "colorCustom9", "colorCustom10", "colorCustom11", "colorCustom12",
    "colorCustom13", "colorCustom14", "colorCustom15", "colorCustom16",
    "colorBlack", "colorBrown", "colorDarkOliveGreen", "colorDarkGreen",
    "colorDarkTeal", "colorDarkBlue", "colorIndigo", "colorDarkGrey",
    "colorDarkRed", "colorOrange", "colorDarkYellow", "colorGreen",
    "colorTeal", "colorBlue", "colorBlueGrey", "colorGrey40",
    "colorRed", "colorLightOrange", "colorLime", "colorSeaGreen",
    "colorAqua", "colorLightBlue", "colorViolet", "colorGrey50",
    "colorPink", "colorGold", "colorYellow", "colorBrightGreen",
    "colorTurquoise", "colorSkyblue", "colorPlum", "colorLightGrey",
    "colorRose", "colorTan", "colorLightYellow", "colorPaleGreen",
    "colorPaleTurquoise", "colorPaleBlue", "colorLavender", "colorWhite",
}

NONEXISTENT_COLORS: Dict[str, str] = {
    "colorCyan": "Use colorAqua instead",
    "colorSilver": "Use colorLightGrey instead",
    "colorPurple": "Use colorViolet or colorIndigo instead",
    "colorMagenta": "Use colorPink or colorViolet instead",
    "colorDefault": "Not in this palette; use colorBlack or colorWhite instead",
    "colorGray": "Use colorGrey40 or colorGrey50 instead",
    "colorGray40": "Use colorGrey40 instead",
    "colorGray50": "Use colorGrey50 instead",
}


# ====================== STYLE CONSTANTS ======================
VALID_PLOT_STYLES: Set[str] = {
    "styleLine", "styleThick", "styleDotted", "styleDashed",
    "styleBar", "styleCandle", "styleDots", "styleHistogram",
    "styleArea", "styleOwnScale", "styleLeftAxisScale",
    "styleHidden", "styleNoRescale", "styleClipMinMax", "styleNoLabel",
    "styleNoLine", "styleNoDraw", "styleStaircase", "styleSwingDots",
    "stylePointAndFigure", "styleLog", "styleNoTitle",
    "styleGradient", "styleCloud",
}

VALID_SHAPE_CONSTANTS: Set[str] = {
    "shapeNone", "shapeUpArrow", "shapeDownArrow",
    "shapeHollowUpArrow", "shapeHollowDownArrow",
    "shapeUpTriangle", "shapeDownTriangle",
    "shapeSmallUpTriangle", "shapeSmallDownTriangle",
    "shapeHollowUpTriangle", "shapeHollowDownTriangle",
    "shapeCircle", "shapeHollowCircle", "shapeSmallCircle",
    "shapeHollowSmallCircle",
    "shapeSquare", "shapeHollowSquare", "shapeSmallSquare",
    "shapeHollowSmallSquare", "shapeHollowSmallUpTriangle",
    "shapeHollowSmallDownTriangle",
    "shapeStar", "shapeHollowStar",
    "shapePositionAbove", "shapePositionAbsolute",
    "shapeDigit0", "shapeDigit1", "shapeDigit2", "shapeDigit3",
    "shapeDigit4", "shapeDigit5", "shapeDigit6", "shapeDigit7",
    "shapeDigit8", "shapeDigit9",
}


# ====================== TIMEFRAME CONSTANTS ======================
TIMEFRAME_CONSTANTS: Set[str] = {
    "inDaily", "inWeekly", "inMonthly", "inQuarterly", "inYearly",
    "in1Minute", "in5Minute", "in15Minute", "in30Minute",
    "inHourly", "in2Hour", "in4Hour",
    "in1Second", "in5Second", "in10Second", "in15Second", "in30Second",
}

COMPRESS_MODES: Set[str] = {
    "compressLast", "compressFirst", "compressHigh", "compressLow",
    "compressVolume", "compressOpen",
}
EXPAND_MODES: Set[str] = {
    "expandLast", "expandFirst", "expandPoint",
}


# ====================== PRICE ARRAYS & VARIABLES ======================
PRICE_ARRAYS: Set[str] = {
    "Open", "High", "Low", "Close", "Volume", "OpenInt",
    "O", "H", "L", "C", "V", "OI", "Average", "A",
}

SIGNAL_OUTPUTS: Set[str] = {
    "Buy", "Sell", "Short", "Cover",
    "BuyPrice", "SellPrice", "ShortPrice", "CoverPrice",
    "Filter", "PositionSize", "PositionScore", "Title",
}

READ_ONLY_VARS: Set[str] = PRICE_ARRAYS | {
    "BarCount", "BarIndex", "Name", "FullName", "DateTime", "Now",
    "Interval", "LastValue", "SelectedValue",
}

GRAPH_VARS: Set[str] = {
    "Graph0", "Graph1", "Graph2", "Graph3", "Graph4",
    "Graph5", "Graph6", "Graph7", "Graph8", "Graph9",
    "GraphXSpace", "GraphZOrder", "GraphGridZOrder", "GraphLabelDecimals",
}

COLUMN_VARS: Set[str] = set()
for i in range(20):
    COLUMN_VARS.add(f"column{i}")
    COLUMN_VARS.add(f"column{i}name")
    COLUMN_VARS.add(f"column{i}format")


# ====================== CONTROL FLOW KEYWORDS ======================
CONTROL_KEYWORDS: Set[str] = {
    "if", "else", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "function", "procedure", "return",
    "local", "global", "static", "extern",
    "try", "catch", "throw",
}

PREPROCESSOR_DIRECTIVES: Set[str] = {
    "#include", "#include_once", "#pragma",
}


# ====================== CONSTANTS ======================
BUILTIN_CONSTANTS: Set[str] = {
    "True", "False", "Null", "NaN", "Pi",
    "NumColumns", "MaxGraph", "BarCount",
    "spsShares", "spsPercentOfEquity", "spsValue", "spsNoChange",
    "spsPercentOfPosition",
    "stopTypeLoss", "stopTypeProfit", "stopTypeTrailing", "stopTypeNBar",
    "stopModePoint", "stopModePercent", "stopModeTick",
    "categoryMarket", "categorySector", "categoryIndustry",
    "categoryGroup", "categoryWatchlist", "categoryFavorite",
    "chartShowDates", "chartShowArrows", "chartShowValues",
    "chartLogarithmic", "chartSessionBreaks",
    "colorBarNone",
    "layerDefault", "layerBack", "layerMid", "layerFront",
    "firHann", "firHamming", "firBlackman", "firFlatTop",
    "firBartlett", "firNone",
}

LOGICAL_OPS: Set[str] = {"AND", "OR", "NOT"}


# ====================== ALL BUILT-IN FUNCTIONS ======================
ZERO_ARG_FUNCTIONS: Set[str] = {
    "OBV", "ADLine", "AccDist", "Chaikin",
    "FullName", "Name", "Now", "GetChartID",
    "BarIndex", "DateTime", "DayOfWeek", "DayOfYear",
    "AdvIssues", "DecIssues", "UncIssues",
    "AdvVolume", "DecVolume", "UncVolume",
    "Trin", "Trix", "Ultimate", "OscP", "OscV",
    "GapUp", "GapDown", "Inside", "Outside",
    "BeginValue", "EndValue",
    "Interval", "TimeNum", "DateNum", "Date", "Day", "Month", "Year",
    "Hour", "Minute", "Second", "MicroSec", "MilliSec",
    "SectorID", "IndustryID", "GroupID", "MarketID",
    "Version", "GetChartBkColor", "GetDatabaseName", "GetFormulaPath",
    "GetBaseIndex", "GetPlaybackDateTime", "GetPriceStyle",
    "GetPerformanceCounter", "GetLastOSError",
    "ClipboardGet", "GetAsyncKeyState",
    "GetCursorMouseButtons", "GetCursorXPosition", "GetCursorYPosition",
    "IsContinuous", "IsFavorite", "IsIndex",
    "LastVisibleValue", "FirstVisibleValue", "HighestVisibleValue", "LowestVisibleValue",
    "DaysSince1900", "NoteGet",
    "StaticVarCount",
    "VoiceCount",
    "InWatchListName",
    "_SECTION_NAME", "_PARAM_VALUES", "_DEFAULT_NAME",
    "GicsID", "IcbID",
    "RWI", "PVI", "NVI",
}

SINGLE_ARG_FUNCTIONS: Dict[str, str] = {
    "RSI": "period", "ATR": "period", "ADX": "period",
    "CCI": "period", "MFI": "period",
    "PDI": "period", "MDI": "period",
    "StochK": "period", "StochD": "period",
    "TRIX": "period", "RMI": "period",
    "RWIHi": "period", "RWILo": "period",
    "SelectedValue": "array", "LastValue": "array",
    "abs": "value", "sqrt": "value", "exp": "value", "log": "value", "log10": "value",
    "sin": "value", "cos": "value", "tan": "value", "cosh": "value", "sinh": "value", "tanh": "value",
    "asin": "value", "acos": "value", "atan": "value",
    "floor": "value", "ceil": "value", "sign": "value", "frac": "value", "int": "value",
    "Prec": "value", "Random": "", "Nz": "array", "IsNull": "array", "IsEmpty": "array",
    "IsFinite": "array", "IsNan": "array", "IsTrue": "array",
    "StrLen": "string",
    "DateTimeToStr": "datetime", "StrToLower": "string", "StrToUpper": "string", "StrTrim": "string",
    "StrToNum": "string", "NumToStr": "number", "StrToDateTime": "string",
    "Chr": "code", "Asc": "char",
    "fgetcwd": "", "fdelete": "filename", "fmkdir": "path", "frmdir": "path",
}

TWO_ARG_FUNCTIONS: Dict[str, str] = {
    "MA": "array,period", "EMA": "array,period", "DEMA": "array,period",
    "TEMA": "array,period", "WMA": "array,period", "HMA": "array,period",
    "Wilders": "array,period", "AMA": "array,period", "AMA2": "array,period",
    "ROC": "array,period", "Momentum": "array,period",
    "HHV": "array,period", "LLV": "array,period",
    "Highest": "array,period", "Lowest": "array,period",
    "HHVBars": "array,period", "LLVBars": "array,period",
    "HighestBars": "array,period", "LowestBars": "array,period",
    "StDev": "array,period", "Variance": "array,period",
    "Sum": "array,period", "Cum": "array",
    "Ref": "array,offset", "Diff": "array,period",
    "PercentRank": "array,period",
    "LinearReg": "array,period", "LinRegSlope": "array,period",
    "LinRegIntercept": "array,period", "TSF": "array,period",
    "Correlation": "array1,array2,period",
    "Covariance": "array1,array2,period",
    "Median": "array,period",
    "IIR": "array,period", "FIR": "array,period",
    "CumProd": "array", "SparseCompress": "array", "SparseExpand": "array",
}

MULTI_ARG_FUNCTIONS: Dict[str, Tuple[int, str]] = {
    "MACD": (2, "fast,slow"), "Signal": (3, "fast,slow,signalPeriod"),
    "BBandTop": (3, "array,period,width"), "BBandBot": (3, "array,period,width"),
    "SAR": (2, "step,limit"),
    "Peak": (2, "array,period"), "Trough": (2, "array,period"),
    "PeakBars": (2, "array,period"), "TroughBars": (2, "array,period"),
    "IIf": (3, "condition,trueArr,falseArr"),
    "WriteIf": (3, "condition,trueStr,falseStr"),
    "Cross": (2, "array1,array2"), "ExRem": (2, "array,trigger"),
    "ExRemSpan": (2, "array,span"),
    "Flip": (2, "set,clear"), "BarsSince": (1, "condition"),
    "HighestSince": (2, "condition,array"), "LowestSince": (2, "condition,array"),
    "HighestSinceBars": (2, "condition,array"), "LowestSinceBars": (2, "condition,array"),
    "ValueWhen": (2, "condition,array"), "RelStrength": (1, "symbol"),
    "Foreign": (2, "symbol,field"), "SetForeign": (1, "symbol"),
}

PLOT_FUNCTIONS: Dict[str, Tuple[int, str]] = {
    "Plot": (3, "array,name,color,style"),
    "PlotShapes": (2, "shape,color,yposition,offset"),
    "PlotOHLC": (4, "open,high,low,close,name,color,style"),
    "PlotGrid": (1, "height,color"),
    "PlotText": (4, "text,x,y,color"),
    "PlotForeign": (2, "symbol,name,color,style"),
    "PlotVAPOverlay": (4, "lines,dir,width,color"),
}

PARAM_FUNCTIONS: Dict[str, Tuple[int, str]] = {
    "Param": (4, "name,default,min,max,step"),
    "ParamToggle": (2, "name,options,default"),
    "ParamList": (2, "name,options,index"),
    "ParamColor": (1, "name,default"),
    "ParamStr": (2, "name,default"),
    "ParamDate": (2, "name,default"),
    "Optimize": (4, "name,default,min,max,step"),
}

EXPLORATION_FUNCTIONS: Dict[str, Tuple[int, str]] = {
    "AddColumn": (2, "array,name,format,color,bgcolor,width"),
    "AddTextColumn": (2, "text,name,format,color,bgcolor,width"),
    "AddMultiTextColumn": (3, "selector,texts,name,format,color,bgcolor"),
}

STRING_FUNCTIONS: Set[str] = {
    "StrLen", "StrLeft", "StrRight", "StrMid", "StrFind", "StrReplace",
    "StrFormat", "StrExtract", "StrToNum", "NumToStr",
    "WriteVal", "EncodeColor", "ColorRGB", "ColorHSB",
}

MATH_FUNCTIONS: Set[str] = {
    "abs", "sqrt", "exp", "log", "log10", "round", "floor", "ceil",
    "sign", "frac", "int", "Min", "Max", "Prec", "sin", "cos", "tan",
    "asin", "acos", "atan", "Random",
}

NULL_FUNCTIONS: Set[str] = {
    "IsNull", "IsEmpty", "IsFinite", "IsNan", "IsTrue", "Nz",
}

FILE_FUNCTIONS: Set[str] = {
    "fopen", "fclose", "fgets", "fputs", "feof",
}

STATIC_VAR_FUNCTIONS: Set[str] = {
    "StaticVarGet", "StaticVarSet", "StaticVarAdd", "StaticVarRemove",
    "StaticVarSetText", "StaticVarGetText",
}

CATEGORY_FUNCTIONS: Set[str] = {
    "CategoryAddSymbol", "CategoryRemoveSymbol",
    "CategoryGetName", "CategoryGetSymbols",
    "InWatchList",
}

OLE_FUNCTIONS: Set[str] = {
    "CreateObject", "CreateStaticObject",
    "GetScriptObject", "EnableScript",
}

MATRIX_FUNCTIONS: Set[str] = {
    "Matrix", "MxGetSize", "MxSetBlock", "MxGetBlock",
    "MxIdentity", "MxTranspose", "MxInverse", "MxDet",
    "MxSolve", "MxSort", "MxSortRows", "MxCopy",
    "MxFromString", "MxToString", "MxSum", "MxMult",
}

GUI_FUNCTIONS: Set[str] = {
    "GuiButton", "GuiCheckBox", "GuiEdit", "GuiSlider",
    "GuiLabel", "GuiGroupBox", "GuiRadio", "GuiComboBox",
    "GuiListBox", "GuiImage",
}

BACKTEST_FUNCTIONS: Set[str] = {
    "ApplyStop", "SetTradeDelays", "SetOption", "GetOption",
    "SetPositionSize", "EnableRotationalTrading",
    "SetChartOptions", "SetFormulaName", "SetBarsRequired",
    "Equity", "GetExtraData", "AlertIf", "GetTradingInterface",
}

EXTRA_MISC_FUNCTIONS: Set[str] = {
    "printf", "PlotTextSetFont", "ColorRGB", "ColorHSB", "ColorBlend",
    "EncodeColor", "WriteVal", "NumToStr", "StrToNum", "StrFormat",
    "StrFind", "StrReplace", "StrExtract", "StrMid", "StrLeft", "StrRight",
    "StrToLower", "StrToUpper", "StrTrim", "StrSort", "StrCount", "StrMatch",
    "StrToDateTime", "Chr", "Asc",
    "ClipboardSet", "PlaySound", "ShellExecute", "NoteSet", "NoteGet",
    "PopupWindow", "SendEmail", "Study", "Error",
    "FFT", "FindIndex", "Lookup", "NullCount", "PriceVolDistribution",
    "Prod", "ProdSince", "Remap", "RequestMouseMoveRefresh", "RequestTimedRefresh",
    "Reverse", "SafeDivide", "SetBacktestMode", "SetBarFillColor",
    "SetChartBkColor", "SetChartBkGradientFill", "SetCustomBacktestProc",
    "SetGradientFill", "SetSortColumns", "SetStopPrecedence", "Sort",
    "SparseInterpolate", "StaticVarCompareExchange", "StaticVarGenerateRanks",
    "StaticVarGetRankedSymbols", "StaticVarInfo", "Study", "SumSince",
    "ThreadSleep", "TimeFrameGetPrice", "TimeFrameMode",
    "TrimResultRows", "VarGet", "VarGetText", "VarSet", "VarSetText",
    "XYChartAddPoint", "XYChartSetAxis", "_DT", "_exit",
    "GetBacktesterObject", "GetFnData", "GetFnDataForeign",
    "GetObject", "GetRTDataForeign", "Hold",
    "InGICS", "InICB", "LineArray",
    "TimeFrameSet", "TimeFrameExpand", "TimeFrameRestore", "TimeFrameCompress",
    "EnableTextOutput", "AddRankColumn", "AddRow", "AddSummaryRows",
    "AlmostEqual", "atan2", "erf", "DateTimeAdd", "DateTimeConvert",
    "DateTimeDiff", "DateTimeFormat", "ParamField", "ParamStyle",
    "ParamTime", "ParamTrigger",
    "Kurtosis", "Skewness", "NormDist", "mtRandom", "mtRandomA",
}

EXTRA_GUI_FUNCTIONS: Set[str] = {
    "GuiDateTime", "GuiEnable", "GuiGetCheck", "GuiGetEvent",
    "GuiGetText", "GuiGetValue", "GuiSendKeyEvents", "GuiSetCheck",
    "GuiSetColors", "GuiSetFont", "GuiSetRange", "GuiSetText",
    "GuiSetValue", "GuiSetVisible",
}

EXTRA_FILE_FUNCTIONS: Set[str] = {
    "fdelete", "fdir", "fgetcwd", "fgetstatus", "fmkdir", "frmdir",
}

GFX_FUNCTIONS: Set[str] = {
    "GfxArc", "GfxChord", "GfxCircle", "GfxDrawImage", "GfxDrawText",
    "GfxEllipse", "GfxFillSolidRect", "GfxGetTextWidth", "GfxGradientRect",
    "GfxLineTo", "GfxMoveTo", "GfxPie", "GfxPolygon", "GfxPolyline",
    "GfxRectangle", "GfxRoundRect", "GfxSelectFont", "GfxSelectHatchBrush",
    "GfxSelectPen", "GfxSelectSolidBrush", "GfxSelectStockObject",
    "GfxSetBkColor", "GfxSetBkMode", "GfxSetCoordsMode", "GfxSetOverlayMode",
    "GfxSetPixel", "GfxSetTextAlign", "GfxSetTextColor", "GfxSetZOrder", "GfxTextOut",
}

INTERNET_FUNCTIONS: Set[str] = {
    "InternetClose", "InternetGetStatusCode", "InternetOpenURL",
    "InternetPostRequest", "InternetReadString", "InternetSetAgent",
    "InternetSetHeaders", "InternetSetOption",
}

TTS_FUNCTIONS: Set[str] = {
    "Say", "VoiceCount", "VoiceSelect", "VoiceSetRate",
    "VoiceSetVolume", "VoiceWaitUntilDone",
}

MAP_FUNCTIONS: Set[str] = {
    "MapCreate",
}

CATEGORY_MGMT_FUNCTIONS: Set[str] = {
    "CategoryCreate", "CategoryFind", "CategorySetName",
}

ALL_FUNCTIONS: Set[str] = (
    ZERO_ARG_FUNCTIONS |
    set(SINGLE_ARG_FUNCTIONS.keys()) |
    set(TWO_ARG_FUNCTIONS.keys()) |
    set(MULTI_ARG_FUNCTIONS.keys()) |
    set(PLOT_FUNCTIONS.keys()) |
    set(PARAM_FUNCTIONS.keys()) |
    set(EXPLORATION_FUNCTIONS.keys()) |
    STRING_FUNCTIONS | MATH_FUNCTIONS | FILE_FUNCTIONS |
    STATIC_VAR_FUNCTIONS | CATEGORY_FUNCTIONS | OLE_FUNCTIONS |
    MATRIX_FUNCTIONS | GUI_FUNCTIONS | BACKTEST_FUNCTIONS |
    NULL_FUNCTIONS | MAP_FUNCTIONS | TTS_FUNCTIONS |
    INTERNET_FUNCTIONS | EXTRA_GUI_FUNCTIONS | EXTRA_FILE_FUNCTIONS |
    EXTRA_MISC_FUNCTIONS | GFX_FUNCTIONS | CATEGORY_MGMT_FUNCTIONS
)


# ====================== VALID SETOPTION FIELDS ======================
VALID_SETOPTION_FIELDS: Set[str] = {
    "InitialEquity", "CommissionMode", "CommissionAmount",
    "MaxOpenPositions", "MaxOpenPositionsLong", "MaxOpenPositionsShort",
    "AllowSameBarEntry", "AllowSameBarExit",
    "HoldMinBars", "ActivateStopsImmediately",
    "FuturesMode", "AccountMargin",
    "UseCloseOnlyForLong", "UseCloseOnlyForShort",
    "UsePrevBarEquityForPosSizing", "AllowPositionShrinking",
    "WorstRankHeld", "AdditionalSentencesDelay",
    "ExtraColumnsLocation", "MinShares", "MinPosValue",
    "RoundLotSize", "TickSize", "MarginDeposit", "PointValue",
    "DisableRibbonUI", "RefreshFlag",
}

VALID_GETOPTION_FIELDS: Set[str] = VALID_SETOPTION_FIELDS | {
    "BarCount", "PortfolioEquity", "PositionCount",
}

VALID_GETRTDATA_FIELDS: Set[str] = {
    "Last", "Change", "Open", "High", "Low", "Volume",
    "Bid", "Ask", "BidSize", "AskSize",
    "AvgVolume", "Shares", "High52", "Low52",
}


# ====================== CASCADE ERROR PATTERNS ======================
CASCADE_PATTERNS = {
    "missing_semicolon": {
        "triggers": [30, 31, 32],
        "cascades_to": [30, 31],
        "desc": "Missing semicolon causes cascading syntax errors"
    },
    "unbalanced_parens": {
        "triggers": [30],
        "cascades_to": [30, 31, 16, 17],
        "desc": "Unbalanced parentheses cause multiple errors"
    },
    "array_in_if": {
        "triggers": [6],
        "cascades_to": [6, 7, 30],
        "desc": "Array in if() condition cascades to type errors"
    },
    "wrong_signature": {
        "triggers": [16],
        "cascades_to": [5, 16, 17],
        "desc": "Wrong function signature cascades to argument errors"
    },
}


# ====================== HALLUCINATED FUNCTION NAMES ======================
HALLUCINATED_NAMES: Dict[str, str] = {
    "MovingAverage": "MA",
    "ExponentialMA": "EMA",
    "WeightedMA": "WMA",
    "DoubleEMA": "DEMA",
    "TripleEMA": "TEMA",
    "HullMA": "HMA",
    "BollingerBands": "BBandTop/BBandBot",
    "BollingerBandTop": "BBandTop",
    "BollingerBandBot": "BBandBot",
    "BollingerUpper": "BBandTop",
    "BollingerLower": "BBandBot",
    "GetRSI": "RSI",
    "RelativeStrengthIndex": "RSI",
    "RelativeStrength": "RSI",
    "AverageTrueRange": "ATR",
    "TrueRange": "ATR",
    "AverageDirectionalIndex": "ADX",
    "DirectionalIndex": "ADX",
    "CommodityChannelIndex": "CCI",
    "MoneyFlowIndex": "MFI",
    "StochasticK": "StochK",
    "StochasticD": "StochD",
    "Stochastic": "StochK/StochD",
    "MACDLine": "MACD",
    "SignalLine": "Signal",
    "MACDSignal": "Signal",
    "CrossOver": "Cross",
    "Crossover": "Cross",
    "ValueWhenCondition": "ValueWhen",
    "HighestValue": "Highest",
    "LowestValue": "Lowest",
    "HighestHigh": "HHV",
    "LowestLow": "LLV",
    "StandardDeviation": "StDev",
    "StdDev": "StDev",
    "OnBalanceVolume": "OBV",
    "AccumulationDistribution": "ADLine",
    "RateOfChange": "ROC",
    "ChandeMomentumOscillator": "CMO",
    "WilliamsR": "WilliamsPercentR",
    "ParabolicSAR": "SAR",
    "LinearRegression": "LinearReg",
    "LinReg": "LinearReg",
    "TimeSeriesForecast": "TSF",
    "Summation": "Sum",
    "CumulativeSum": "Cum",
    "Cumulative": "Cum",
    "Reference": "Ref",
    "PreviousBar": "Ref(Close,-1)",
    "ImmediateIf": "IIf",
    "ConditionalIf": "IIf",
    "WriteConditional": "WriteIf",
    "RemoveConsecutive": "ExRem",
    "BarsSinceCondition": "BarsSince",
    "ValueOnCondition": "ValueWhen",
    "FlipSignal": "Flip",
    "RandomNumber": "Random",
    "RoundToDecimal": "round",
    "RoundDown": "floor",
    "RoundUp": "ceil",
    "AbsoluteValue": "abs",
    "SquareRoot": "sqrt",
    "NaturalLog": "log",
    "LogBase10": "log10",
    "Exponential": "exp",
    "Power": "^",
    "IntegerPart": "int",
    "FractionalPart": "frac",
    "StringFormat": "StrFormat",
    "StringLength": "StrLen",
    "StringLeft": "StrLeft",
    "StringRight": "StrRight",
    "StringMid": "StrMid",
    "StringFind": "StrFind",
    "StringReplace": "StrReplace",
    "StringExtract": "StrExtract",
    "NumberToString": "NumToStr",
    "StringToNumber": "StrToNum",
    "PlotChart": "Plot",
    "PlotCandlestick": "PlotOHLC",
    "PlotShape": "PlotShapes",
    "AddExplorerColumn": "AddColumn",
    "AddTextExplorerColumn": "AddTextColumn",
    "SetParameters": "Param",
    "SetParameter": "Param",
    "Optimization": "Optimize",
    "ApplyStops": "ApplyStop",
    "SetDelays": "SetTradeDelays",
    "TradeDelay": "SetTradeDelays",
    "SetPosition": "SetPositionSize",
    "EnableRotational": "EnableRotationalTrading",
    "RotationalTrading": "EnableRotationalTrading",
    "StaticVariableGet": "StaticVarGet",
    "StaticVariableSet": "StaticVarSet",
    "StaticVariableAdd": "StaticVarAdd",
    "FileOpen": "fopen",
    "FileClose": "fclose",
    "FileRead": "fgets",
    "FileWrite": "fputs",
    "FileEnd": "feof",
}


# ====================== WRONG COLOR PATTERNS ======================
WRONG_COLOR_PATTERNS: Dict[str, str] = {
    "color_green": "colorGreen", "color_red": "colorRed",
    "color_blue": "colorBlue", "color_yellow": "colorYellow",
    "color_orange": "colorOrange", "color_black": "colorBlack",
    "color_white": "colorWhite", "color_grey": "colorGrey",
    "color_gray": "colorGrey", "color_darkgreen": "colorDarkGreen",
    "color_darkred": "colorDarkRed", "color_darkblue": "colorDarkBlue",
    "color_lightgreen": "colorLightGreen", "color_lightblue": "colorLightBlue",
    "color_lightyellow": "colorLightYellow", "color_lightgrey": "colorLightGrey",
    "color_lightgray": "colorLightGrey", "color_brightgreen": "colorBrightGreen",
    "color_palegreen": "colorPaleGreen", "color_seagreen": "colorSeaGreen",
    "color_darkyellow": "colorDarkYellow", "color_darkgrey": "colorDarkGrey",
    "color_darkgray": "colorDarkGrey", "color_gold": "colorGold",
    "color_pink": "colorPink", "color_turquoise": "colorTurquoise",
    "color_violet": "colorViolet", "color_plum": "colorPlum",
    "color_lavender": "colorLavender", "color_lime": "colorLime",
    "color_tan": "colorTan", "color_rose": "colorRose",
    "color_indigo": "colorIndigo", "color_teal": "colorTeal",
    "color_navy": "colorNavy", "color_olive": "colorOlive",
    "color_coral": "colorCoral", "color_crimson": "colorCrimson",
    "color_salmon": "colorSalmon", "color_skyblue": "colorSkyblue",
    "color_aqua": "colorAqua",
    "clrGreen": "colorGreen", "clrRed": "colorRed",
    "clrBlue": "colorBlue", "clrYellow": "colorYellow",
    "clrBlack": "colorBlack", "clrWhite": "colorWhite",
    "clrOrange": "colorOrange", "clrGrey": "colorGrey",
    "clrGray": "colorGrey", "clrPink": "colorPink",
    "green": "colorGreen", "red": "colorRed",
    "blue": "colorBlue", "yellow": "colorYellow",
    "orange": "colorOrange", "black": "colorBlack",
    "white": "colorWhite", "grey": "colorGrey",
    "gray": "colorGrey",
}


# ====================== WRONG STYLE PATTERNS ======================
WRONG_STYLE_PATTERNS: Dict[str, str] = {
    "style_line": "styleLine", "style_thick": "styleThick",
    "style_dotted": "styleDotted", "style_dashed": "styleDashed",
    "style_bar": "styleBar", "style_candle": "styleCandle",
    "style_dots": "styleDots", "style_histogram": "styleHistogram",
    "style_area": "styleArea", "style_hidden": "styleHidden",
    "style_ownscale": "styleOwnScale", "style_own_scale": "styleOwnScale",
    "style_no_label": "styleNoLabel", "style_no_rescale": "styleNoRescale",
    "style_no_line": "styleNoLine", "style_no_draw": "styleNoDraw",
    "style_staircase": "styleStaircase", "style_swingdots": "styleSwingDots",
    "style_swing_dots": "styleSwingDots", "style_pointandfigure": "stylePointAndFigure",
    "style_point_and_figure": "stylePointAndFigure",
    "styleLogScale": "styleLog", "styleLogscale": "styleLog",
    "styleCandleStick": "styleCandle", "styleCandlestick": "styleCandle",
    "styleBarChart": "styleBar", "styleLineChart": "styleLine",
}


# ====================== WRONG SHAPE PATTERNS ======================
WRONG_SHAPE_PATTERNS: Dict[str, str] = {
    "shape_arrow_up": "shapeUpArrow", "shape_arrow_down": "shapeDownArrow",
    "shape_arrowup": "shapeUpArrow", "shape_arrowdown": "shapeDownArrow",
    "shape_arrowUp": "shapeUpArrow", "shape_arrowDown": "shapeDownArrow",
    "shape_up_arrow": "shapeUpArrow", "shape_down_arrow": "shapeDownArrow",
    "shape_triangle_up": "shapeUpTriangle", "shape_triangle_down": "shapeDownTriangle",
    "shape_triangleup": "shapeUpTriangle", "shape_triangledown": "shapeDownTriangle",
    "shape_up_triangle": "shapeUpTriangle", "shape_down_triangle": "shapeDownTriangle",
    "shape_cross": "shapeSmallCross", "shape_diamond": "shapeSmallSquare",
    "shape_number0": "shapeDigit0", "shape_number1": "shapeDigit1",
    "shape_number2": "shapeDigit2", "shape_number3": "shapeDigit3",
    "shape_number4": "shapeDigit4", "shape_number5": "shapeDigit5",
    "shape_number6": "shapeDigit6", "shape_number7": "shapeDigit7",
    "shape_number8": "shapeDigit8", "shape_number9": "shapeDigit9",
}


# ====================== MAIN VALIDATOR CLASS ======================
class AFLValidator:
    """Comprehensive AFL syntax and semantic validator."""

    def __init__(self):
        self.defined_vars: Set[str] = set()
        self.defined_funcs: Set[str] = set()
        self.used_funcs: Set[str] = set()
        self.user_funcs: Dict[str, int] = {}
        self.all_known: Set[str] = (
            ALL_FUNCTIONS | BUILTIN_CONSTANTS | PRICE_ARRAYS | SIGNAL_OUTPUTS |
            GRAPH_VARS | COLUMN_VARS | READ_ONLY_VARS | LOGICAL_OPS |
            VALID_COLORS | VALID_PLOT_STYLES | VALID_SHAPE_CONSTANTS |
            TIMEFRAME_CONSTANTS | COMPRESS_MODES | EXPAND_MODES |
            CONTROL_KEYWORDS | VALID_SETOPTION_FIELDS | VALID_GETOPTION_FIELDS |
            VALID_GETRTDATA_FIELDS
        )

    def validate(self, code: str) -> ValidationResult:
        """Main validation entry point. Returns structured ValidationResult."""
        self.defined_vars = set()
        self.defined_funcs = set()
        self.used_funcs = set()
        self.user_funcs = {}
        issues: List[Issue] = []
        lines = code.split('\n')
        clean = self._remove_comments(code)

        # Phase 1: Syntax-level checks
        self._check_brackets(code, lines, issues)
        self._check_escape_sequences(clean, lines, issues)
        self._check_unary_plus(clean, lines, issues)
        self._check_preprocessor(clean, lines, issues)

        # Phase 2: Collect definitions
        self._collect_definitions(clean, lines)

        # Phase 3: Semantic checks
        self._check_colors(clean, lines, issues)
        self._check_styles(clean, lines, issues)
        self._check_shapes(clean, lines, issues)
        self._check_functions(clean, lines, issues)
        self._check_function_signatures(clean, lines, issues)
        self._check_hallucinated_names(clean, lines, issues)
        self._check_single_arg_funcs(clean, lines, issues)
        self._check_zero_arg_funcs(clean, lines, issues)
        self._check_argument_counts(clean, lines, issues)

        # Phase 4: Variable and type checks
        self._check_reserved_keywords(clean, lines, issues)
        self._check_read_only(clean, lines, issues)
        self._check_undefined_variables(clean, lines, issues)
        self._check_type_mismatches(clean, lines, issues)
        self._check_subscript_errors(clean, lines, issues)

        # Phase 5: Logic and conditional checks
        self._check_assignment_vs_equality(clean, lines, issues)
        self._check_if_with_arrays(clean, lines, issues)
        self._check_iif_vs_writeif(clean, lines, issues)
        self._check_if_else_with_strings(clean, lines, issues)
        self._check_loop_errors(clean, lines, issues)

        # Phase 6: Multi-timeframe checks
        self._check_timeframe(clean, lines, issues)

        # Phase 7: Backtest and trading checks
        self._check_backtest_signals(clean, lines, issues)
        self._check_rotational_trading(clean, lines, issues)
        self._check_applystop(clean, lines, issues)
        self._check_setoption_fields(clean, lines, issues)
        self._check_position_sizing(clean, lines, issues)

        # Phase 8: Optimization checks
        self._check_optimization(clean, lines, issues)

        # Phase 9: File I/O checks
        self._check_file_io(clean, lines, issues)

        # Phase 10: OLE/COM checks
        self._check_ole_warnings(clean, lines, issues)

        # Phase 11: Plot and efficiency checks
        self._check_plot_efficiency(clean, lines, issues)
        self._check_exrem(clean, lines, issues)

        # Phase 12: Matrix checks
        self._check_matrix(clean, lines, issues)

        # Phase 13: Cascading error detection
        self._detect_cascading_errors(issues, clean, lines)

        # Phase 14: Shadowing checks
        self._check_shadowing(clean, lines, issues)

        # Phase 15: Param/Optimize pattern checks
        self._check_param_patterns(clean, lines, issues)

        # Phase 16: String checks
        self._check_string_operations(clean, lines, issues)

        # Phase 17: GetRTData checks
        self._check_getrtdata(clean, lines, issues)

        # Phase 18: Category checks
        self._check_category_functions(clean, lines, issues)

        # Phase 19: Function argument type checks
        self._check_function_arg_types(clean, lines, issues)

        # Sort by line number
        issues.sort(key=lambda i: (i.line, i.severity.value))

        # Build result
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in issues if i.severity == Severity.INFO)
        suggestion_count = sum(1 for i in issues if i.severity == Severity.SUGGESTION)
        cascade_count = sum(1 for i in issues if i.cascading)

        return ValidationResult(
            is_valid=(error_count == 0),
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            suggestion_count=suggestion_count,
            cascade_count=cascade_count,
            issues=issues,
        )

    # ====================== UTILITY METHODS ======================
    def _remove_comments(self, code: str) -> str:
        result = re.sub(r'/\*.*?\*/', ' ', code, flags=re.DOTALL)
        result = re.sub(r'//[^\n]*', ' ', result)
        return result

    def _find_line(self, lines: List[str], pattern: str, start: int = 0) -> int:
        for i, line in enumerate(lines[start:], start + 1):
            if pattern in line:
                return i
        return 0

    def _find_line_re(self, lines: List[str], pattern: str, start: int = 0) -> int:
        for i, line in enumerate(lines[start:], start + 1):
            if re.search(pattern, line):
                return i
        return 0

    def _count_args(self, args_str: str) -> int:
        if not args_str or not args_str.strip():
            return 0
        depth = 0
        count = 1
        for ch in args_str:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 0:
                count += 1
        return count if depth == 0 else count

    # ====================== PHASE 1: SYNTAX CHECKS ======================
    def _check_brackets(self, code: str, lines: List[str], issues: List[Issue]):
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0
        paren_line = bracket_line = brace_line = 0
        in_string = False
        in_line_comment = False
        in_block_comment = False
        escape_next = False

        for line_num, line in enumerate(lines, 1):
            in_line_comment = False
            for i, ch in enumerate(line):
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if in_block_comment:
                    if ch == '*' and i + 1 < len(line) and line[i + 1] == '/':
                        in_block_comment = False
                    continue
                if in_line_comment:
                    continue
                if ch == '/' and i + 1 < len(line):
                    if line[i + 1] == '/':
                        in_line_comment = True
                        continue
                    if line[i + 1] == '*':
                        in_block_comment = True
                        continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '(':
                    paren_depth += 1
                    if paren_depth == 1:
                        paren_line = line_num
                elif ch == ')':
                    paren_depth -= 1
                    if paren_depth < 0:
                        issues.append(Issue(line_num, i, Severity.ERROR,
                            "Bracket", "[ERROR_30] Extra closing parenthesis ')'",
                            "Remove extra ')' or add matching '('"))
                        paren_depth = 0
                elif ch == '[':
                    bracket_depth += 1
                    if bracket_depth == 1:
                        bracket_line = line_num
                elif ch == ']':
                    bracket_depth -= 1
                    if bracket_depth < 0:
                        issues.append(Issue(line_num, i, Severity.ERROR,
                            "Bracket", "[ERROR_30] Extra closing bracket ']'",
                            "Remove extra ']' or add matching '['"))
                        bracket_depth = 0
                elif ch == '{':
                    brace_depth += 1
                    if brace_depth == 1:
                        brace_line = line_num
                elif ch == '}':
                    brace_depth -= 1
                    if brace_depth < 0:
                        issues.append(Issue(line_num, i, Severity.ERROR,
                            "Bracket", "[ERROR_30] Extra closing brace '}'",
                            "Remove extra '}' or add matching '{'"))
                        brace_depth = 0

        if paren_depth > 0:
            issues.append(Issue(paren_line, 0, Severity.ERROR,
                "Bracket", f"[ERROR_30] {paren_depth} unclosed parenthesis '(' at line {paren_line}",
                "Add closing ')' to match"))
        if bracket_depth > 0:
            issues.append(Issue(bracket_line, 0, Severity.ERROR,
                "Bracket", f"[ERROR_30] {bracket_depth} unclosed bracket '[' at line {bracket_line}",
                "Add closing ']' to match"))
        if brace_depth > 0:
            issues.append(Issue(brace_line, 0, Severity.ERROR,
                "Bracket", f"[ERROR_30] {brace_depth} unclosed brace '{{' at line {brace_line}",
                "Add closing '}}' to match"))

    def _check_escape_sequences(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'"([^"\\]|\\.)*"', clean):
            string_content = m.group(0)
            invalid_escapes = re.findall(r'\\[^nrt"\\]', string_content)
            for esc in invalid_escapes:
                ln = self._find_line(lines, esc)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "String", f"[ERROR_54] Incorrect escape sequence '\\{esc[1]}'",
                    "Only \\n, \\r, \\t, \\\\, \\\" are supported"))

    def _check_unary_plus(self, clean: str, lines: List[str], issues: List[Issue]):
        """Detect unary '+' on numeric literals — AmiBroker rejects this with Error 30.

        Examples flagged:
            PlotShapes(... , 0, High, +15);    // arg position
            Ref(Close, +1);                    // arg position
            a = +15;                           // assignment RHS
            if (x == +1) ...                   // comparison RHS
        Examples NOT flagged (binary plus is legal):
            a + 15        f() + 1        High + 0.5
        """
        # Strip string literals so a literal '+' inside "..." can't false-positive.
        no_strings = re.sub(r'"([^"\\]|\\.)*"', lambda m: '"' + ' ' * (len(m.group(0)) - 2) + '"', clean)

        # Reportable preceding-context characters: whitespace-stripped char must be one of these.
        UNARY_CONTEXT = set(",(=<>!?[{;:&|\n")

        seen_lines: Set[int] = set()
        for m in re.finditer(r'\+\s*\d', no_strings):
            idx = m.start()
            # Walk back over whitespace to find the prior non-space char.
            j = idx - 1
            while j >= 0 and no_strings[j] in ' \t':
                j -= 1
            if j < 0:
                prev = '\n'
            else:
                prev = no_strings[j]

            is_unary = prev in UNARY_CONTEXT

            # Also flag when '+' follows a keyword like 'return' or 'else'.
            if not is_unary and j >= 0:
                kw_match = re.search(r'\b(return|else|then)\s*$', no_strings[:idx])
                if kw_match:
                    is_unary = True

            if not is_unary:
                continue

            ln = no_strings[:idx].count('\n') + 1
            if ln in seen_lines:
                continue
            seen_lines.add(ln)

            # Pull the offending token for the message.
            tok_m = re.match(r'\+\s*(\d[\d.]*)', no_strings[idx:])
            tok = tok_m.group(0) if tok_m else '+N'
            num = tok_m.group(1) if tok_m else 'N'
            issues.append(Issue(
                ln, 0, Severity.ERROR,
                "Syntax",
                f"[ERROR_30] Unary '+' on numeric literal '{tok}' — AmiBroker rejects this with Syntax error, unexpected '+'",
                f"Drop the '+' sign. Positive numbers carry no sign; write `{num}` instead of `{tok}`. Only negative numbers carry '-'.",
            ))

    def _check_preprocessor(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'#include\s+"([^"]+)"', clean):
            filename = m.group(1)
            ln = self._find_line(lines, filename)
            if not os.path.exists(filename):
                issues.append(Issue(ln, 0, Severity.WARNING,
                    "Include", f"[ERROR_42] #include file not found: {filename}",
                    "Check file path exists"))

    # ====================== PHASE 2: COLLECT DEFINITIONS ======================
    def _collect_definitions(self, clean: str, lines: List[str]):
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*=', clean):
            self.defined_vars.add(m.group(1))
        for m in re.finditer(r'\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)', clean):
            fname = m.group(1)
            params = [p.strip() for p in m.group(2).split(',') if p.strip()]
            self.defined_funcs.add(fname)
            self.user_funcs[fname] = len(params)
        for m in re.finditer(r'\bprocedure\s+([A-Za-z_]\w*)\s*\(([^)]*)\)', clean):
            fname = m.group(1)
            params = [p.strip() for p in m.group(2).split(',') if p.strip()]
            self.defined_funcs.add(fname)
            self.user_funcs[fname] = len(params)

    # ====================== PHASE 3: SEMANTIC CHECKS ======================
    def _check_colors(self, clean: str, lines: List[str], issues: List[Issue]):
        for wrong, correct in WRONG_COLOR_PATTERNS.items():
            if re.search(r'\b' + re.escape(wrong) + r'\b', clean):
                ln = self._find_line(lines, wrong)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Color", f"Invalid color '{wrong}'",
                    f"Use '{correct}' instead"))
        for wrong, suggestion in NONEXISTENT_COLORS.items():
            if re.search(r'\b' + re.escape(wrong) + r'\b', clean):
                ln = self._find_line(lines, wrong)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Color", f"Color '{wrong}' does not exist in AmiBroker",
                    suggestion))
        for m in re.finditer(r'\b(color[A-Z][A-Za-z0-9_]*)\b', clean):
            cname = m.group(1)
            if cname not in VALID_COLORS and cname not in NONEXISTENT_COLORS:
                if not re.search(re.escape(cname) + r'\s*=\s*ColorRGB', clean):
                    ln = self._find_line(lines, cname)
                    issues.append(Issue(ln, 0, Severity.WARNING,
                        "Color", f"Unknown color constant '{cname}'",
                        "Verify color exists or define with ColorRGB(r,g,b)"))

    def _check_styles(self, clean: str, lines: List[str], issues: List[Issue]):
        for wrong, correct in WRONG_STYLE_PATTERNS.items():
            if re.search(r'\b' + re.escape(wrong) + r'\b', clean):
                ln = self._find_line(lines, wrong)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Style", f"Invalid style '{wrong}'",
                    f"Use '{correct}' instead"))
        for m in re.finditer(r'\b(style[A-Z][A-Za-z0-9_]*)\b', clean):
            sname = m.group(1)
            if sname not in VALID_PLOT_STYLES:
                ln = self._find_line(lines, sname)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Style", f"Invalid plot style '{sname}'",
                    "Use styleLine, styleCandle, styleBar, etc."))

    def _check_shapes(self, clean: str, lines: List[str], issues: List[Issue]):
        for wrong, correct in WRONG_SHAPE_PATTERNS.items():
            if re.search(r'\b' + re.escape(wrong) + r'\b', clean):
                ln = self._find_line(lines, wrong)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Shape", f"Invalid shape '{wrong}'",
                    f"Use '{correct}' instead"))
        for m in re.finditer(r'\b(shape[A-Z][A-Za-z0-9_]*)\b', clean):
            sname = m.group(1)
            if sname not in VALID_SHAPE_CONSTANTS:
                ln = self._find_line(lines, sname)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Shape", f"Invalid shape constant '{sname}'",
                    "Use shapeUpArrow, shapeDownArrow, shapeCircle, etc."))

    def _check_functions(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'\b([A-Z][A-Za-z0-9_]*)\s*\(', clean):
            fname = m.group(1)
            if fname in CONTROL_KEYWORDS:
                continue
            if fname in self.defined_funcs:
                continue
            if fname not in ALL_FUNCTIONS:
                ln = self._find_line(lines, fname)
                suggestion = HALLUCINATED_NAMES.get(fname, "")
                msg = f"Unknown function '{fname}'"
                if suggestion:
                    msg += f" - did you mean '{suggestion}'?"
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", msg,
                    f"Use correct AFL function name" + (f": {suggestion}" if suggestion else "")))

    def _check_function_signatures(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'\bPlot\s*\(([^;]+)', clean):
            args_str = m.group(1)
            depth = 1
            end = 0
            for i, ch in enumerate(args_str):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end > 0:
                args_str = args_str[:end]
            arg_count = self._count_args(args_str)
            if arg_count < 3:
                ln = self._find_line(lines, "Plot(")
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", f"[ERROR_17] Plot() requires at least 3 arguments (array, name, color), got {arg_count}",
                    "Plot(array, name, color, style)"))

    def _check_hallucinated_names(self, clean: str, lines: List[str], issues: List[Issue]):
        for wrong, correct in HALLUCINATED_NAMES.items():
            if re.search(r'\b' + re.escape(wrong) + r'\s*\(', clean):
                ln = self._find_line(lines, wrong)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", f"Hallucinated function name '{wrong}()' - AmiBroker uses '{correct}()'",
                    f"Replace '{wrong}()' with '{correct}()'"))

    def _check_single_arg_funcs(self, clean: str, lines: List[str], issues: List[Issue]):
        for func, param_hint in SINGLE_ARG_FUNCTIONS.items():
            pattern = rf'\b{func}\s*\(\s*(?:Close|Open|High|Low|Volume|C|O|H|L|V|[A-Z][a-z]+)\s*,'
            if re.search(pattern, clean):
                ln = self._find_line_re(lines, rf'{func}\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", f"[ERROR_5/16] {func}() takes ONE argument ({param_hint}), not array+period",
                    f"Use {func}(period) not {func}(Close, period)"))

    def _check_zero_arg_funcs(self, clean: str, lines: List[str], issues: List[Issue]):
        for func in ZERO_ARG_FUNCTIONS:
            pattern = rf'\b{func}\s*\(\s*[^)\s]'
            if re.search(pattern, clean):
                ln = self._find_line_re(lines, rf'{func}\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", f"[ERROR_16] {func}() takes ZERO arguments",
                    f"Use {func}() not {func}(something)"))

    def _check_argument_counts(self, clean: str, lines: List[str], issues: List[Issue]):
        all_sig = {**MULTI_ARG_FUNCTIONS, **PLOT_FUNCTIONS, **PARAM_FUNCTIONS, **EXPLORATION_FUNCTIONS}
        for func, (min_args, hint) in all_sig.items():
            pattern = rf'\b{func}\s*\('
            for m in re.finditer(pattern, clean):
                start = m.end()
                depth = 1
                end = start
                while end < len(clean) and depth > 0:
                    if clean[end] == '(':
                        depth += 1
                    elif clean[end] == ')':
                        depth -= 1
                    end += 1
                if depth == 0:
                    args_str = clean[start:end-1].strip()
                    arg_count = self._count_args(args_str)
                    if 0 < arg_count < min_args:
                        ln = self._find_line_re(lines, rf'{func}\s*\(')
                        issues.append(Issue(ln, 0, Severity.ERROR,
                            "Function", f"[ERROR_17] {func}() expects at least {min_args} arguments ({hint}), got {arg_count}",
                            f"Add missing arguments"))

    # ====================== PHASE 4: VARIABLE AND TYPE CHECKS ======================
    def _check_reserved_keywords(self, clean: str, lines: List[str], issues: List[Issue]):
        for var in READ_ONLY_VARS:
            if var in SIGNAL_OUTPUTS:
                continue
            pattern = rf'\b{re.escape(var)}\s*=[^=]'
            if re.search(pattern, clean):
                ln = self._find_line(lines, f"{var} =")
                if ln == 0:
                    ln = self._find_line_re(lines, rf'{re.escape(var)}\s*=')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Reserved", f"'{var}' is read-only — cannot assign to it",
                    "Use a different variable name"))

    def _check_read_only(self, clean: str, lines: List[str], issues: List[Issue]):
        for var in ["BarCount", "Name", "FullName", "DateTime", "Now"]:
            if re.search(rf'\b{var}\s*=[^=]', clean):
                ln = self._find_line(lines, f"{var} =")
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Reserved", f"'{var}' is read-only (ERROR related)",
                    f"Cannot modify {var}"))

    def _check_undefined_variables(self, clean: str, lines: List[str], issues: List[Issue]):
        all_known = (
            self.all_known | self.defined_vars | self.defined_funcs |
            {"AND", "OR", "NOT", "True", "False", "Null"}
        )
        clean_no_strings = re.sub(r'"[^"]*"', '""', clean)
        clean_no_strings = re.sub(r'//[^\n]*', '', clean_no_strings)
        clean_no_strings = re.sub(r'/\*.*?\*/', '', clean_no_strings, flags=re.DOTALL)
        
        skip_funcs = {
            "SetOption", "GetOption", "SetPositionSize", "ApplyStop",
            "SetTradeDelays", "EnableRotationalTrading", "Param", "Optimize",
            "Plot", "PlotShapes", "PlotOHLC", "AddColumn", "AddTextColumn",
            "IIf", "WriteIf", "Cross", "ExRem", "Foreign", "SetForeign",
            "EMA", "RSI", "ATR", "ADX", "MACD", "BBandTop", "BBandBot",
            "MA", "HHV", "LLV", "Ref", "BarsSince", "ValueWhen",
            "StaticVarGet", "StaticVarSet", "TimeFrameSet", "TimeFrameExpand",
        }
        
        for m in re.finditer(r'\b([A-Z][A-Za-z0-9_]*)\b(?!\s*\()', clean_no_strings):
            var = m.group(1)
            if var in all_known:
                continue
            if var.startswith(("color", "style", "shape", "in", "compress", "expand")):
                continue
            if var in CONTROL_KEYWORDS:
                continue
            if var in skip_funcs:
                continue
            ln = self._find_line(lines, var)
            if ln > 0:
                if not re.search(rf'SetOption\(\s*"{re.escape(var)}"', clean):
                    if not re.search(rf'GetOption\(\s*"{re.escape(var)}"', clean):
                        issues.append(Issue(ln, 0, Severity.WARNING,
                            "Variable", f"[ERROR_29] Variable '{var}' may be used without being initialized",
                            f"Define '{var}' before use or check spelling"))

    def _check_type_mismatches(self, clean: str, lines: List[str], issues: List[Issue]):
        if re.search(r'-\s*"', clean):
            ln = self._find_line_re(lines, r'-\s*"')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Type", "[ERROR_3] Unary minus operator requires number or array, not string",
                "Don't negate string values"))
        for m in re.finditer(r'"[^"]*"\s*[*/^%]', clean):
            ln = self._find_line(lines, '"')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Type", "[ERROR_1] Cannot multiply/divide strings",
                "Use numeric operands only"))
        for func in MATH_FUNCTIONS:
            pattern = rf'\b{func}\s*\(\s*"'
            if re.search(pattern, clean):
                ln = self._find_line_re(lines, rf'{func}\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Type", f"[ERROR_2] {func}() requires number or array, not string",
                    f"Pass numeric value to {func}()"))

    def _check_subscript_errors(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'([A-Za-z_]\w*)\s*\[\s*("[^"]*")\s*\]', clean):
            ln = self._find_line(lines, m.group(0))
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Subscript", "[ERROR_9/11] Array subscript must be a number, not a string",
                "Use numeric index: array[0] not array[\"text\"]"))
        for m in re.finditer(r'\[\s*(Close|Open|High|Low|Volume|[A-Z][A-Za-z]+)\s*\]', clean):
            var = m.group(1)
            if var not in {"True", "False", "Null"}:
                ln = self._find_line(lines, f'[{var}]')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Subscript", f"[ERROR_9] Array subscript must be a number, not array '{var}'",
                    "Use numeric index or loop variable"))
        for m in re.finditer(r'"[^"]*"\s*\[', clean):
            ln = self._find_line(lines, '"')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Subscript", "[ERROR_11] Cannot use subscript operator [] on strings",
                "Use StrMid() for string character access"))
        for m in re.finditer(r'\[\s*-\s*\d+\s*\]', clean):
            ln = self._find_line(lines, m.group(0))
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Subscript", "[ERROR_10] Negative subscript - accessing array element below 0",
                "Check subscript is >= 0"))
        for m in re.finditer(r'\[\s*(\d{3,})\s*\]', clean):
            val = int(m.group(1))
            if val > 0:
                ln = self._find_line(lines, m.group(0))
                issues.append(Issue(ln, 0, Severity.WARNING,
                    "Subscript", f"[ERROR_10] Hardcoded subscript [{val}] may exceed BarCount on shorter datasets",
                    "Use BarCount-1 or add bounds check"))

    # ====================== PHASE 5: LOGIC AND CONDITIONAL CHECKS ======================
    def _check_assignment_vs_equality(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'\b(if|while|for)\s*\(([^)]*?)([A-Za-z_]\w*)\s*=\s*([^=][^)]*)\)', clean):
            keyword = m.group(1)
            var_name = m.group(3)
            ln = self._find_line_re(lines, rf'{keyword}\s*\(')
            issues.append(Issue(ln, 0, Severity.WARNING,
                "Logic", f"[WARNING_501] Assignment '{var_name} = ...' inside {keyword}() — did you mean '==' ?",
                f"Use == for comparison: {keyword}({var_name} == value)"))
        for m in re.finditer(r'IIf\s*\(\s*([A-Za-z_]\w*)\s*=\s*([^=])', clean):
            var_name = m.group(1)
            ln = self._find_line(lines, "IIf(")
            issues.append(Issue(ln, 0, Severity.WARNING,
                "Logic", f"[WARNING_501] Assignment '{var_name} = ...' inside IIf() — did you mean '==' ?",
                "Use IIf(var == value, trueVal, falseVal)"))

    def _check_if_with_arrays(self, clean: str, lines: List[str], issues: List[Issue]):
        array_indicators = set(PRICE_ARRAYS) | {"MACD", "RSI", "MA", "EMA", "ATR", "ADX", "CCI",
            "BBandTop", "BBandBot", "StochK", "StochD", "MFI", "OBV", "ROC",
            "HHV", "LLV", "Highest", "Lowest", "Sum", "StDev", "WMA", "DEMA", "TEMA", "HMA"}
        for m in re.finditer(r'\bif\s*\(([^)]+)\)', clean):
            cond = m.group(1)
            for arr in array_indicators:
                if re.search(rf'\b{arr}\b', cond):
                    if not re.search(rf'{arr}\s*\[', cond):
                        ln = self._find_line_re(lines, r'\bif\s*\(')
                        issues.append(Issue(ln, 0, Severity.ERROR,
                            "Conditional", f"[ERROR_6] 'if' condition contains array '{arr}' — use IIf() instead",
                            f"Buy = IIf({arr} > threshold, 1, 0);"))
                        break

    def _check_iif_vs_writeif(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'IIf\s*\([^,]+,\s*"[^"]*"\s*,\s*"[^"]*"', clean):
            ln = self._find_line(lines, "IIf(")
            issues.append(Issue(ln, 0, Severity.ERROR,
                "IIf", "IIf() cannot return strings — use WriteIf() for text output",
                "Title = WriteIf(condition, \"text1\", \"text2\")"))
        for m in re.finditer(r'Title\s*=\s*IIf\s*\(', clean):
            ln = self._find_line(lines, "Title =")
            issues.append(Issue(ln, 0, Severity.WARNING,
                "IIf", "Title should use WriteIf() for string output, not IIf()",
                "Title = WriteIf(condition, \"text\", \"text\")"))

    def _check_if_else_with_strings(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'\b(if|while|for)\s*\(\s*"([^"]*)"', clean):
            keyword = m.group(1)
            ln = self._find_line_re(lines, rf'{keyword}\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Conditional", f"[ERROR_7] Cannot use string as {keyword}() condition",
                f"Use comparison: {keyword}(\"text\" != \"other\")"))

    def _check_loop_errors(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'for\s*\([^)]*BarIndex\(\)[^)]*\)', clean):
            ln = self._find_line_re(lines, r'for\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Loop", "BarIndex() is an array — use BarCount for loop limits",
                "for(i = 0; i < BarCount; i++)"))
        for m in re.finditer(r'for\s*\(\s*[A-Za-z_]\w*\s*=\s*\d+\s*;\s*[A-Za-z_]\w*\s*[<>]=?\s*[^;]+;\s*\)', clean):
            ln = self._find_line_re(lines, r'for\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Loop", "[ERROR_15] For loop missing increment — will run forever",
                "Add increment: for(i = 0; i < N; i++)"))
        for m in re.finditer(r'while\s*\(\s*([A-Za-z_]\w*)\s*[<>]', clean):
            var_name = m.group(1)
            ln = self._find_line_re(lines, r'while\s*\(')
            issues.append(Issue(ln, 0, Severity.WARNING,
                "Loop", f"[ERROR_13] Verify '{var_name}' is incremented in while loop body",
                "Ensure loop variable changes to prevent endless loop"))
        for m in re.finditer(r'for\s*\(\s*[A-Za-z_]\w*\s*=\s*0\s*;\s*[A-Za-z_]\w*\s*<\s*(\d{3,})\b', clean):
            limit = int(m.group(1))
            ln = self._find_line_re(lines, r'for\s*\(')
            issues.append(Issue(ln, 0, Severity.WARNING,
                "Loop", f"[ERROR_10] Hardcoded loop limit {limit} — may exceed BarCount on short datasets",
                "Use AND i < BarCount: for(i = 0; i < min(Period, BarCount); i++)"))

    # ====================== PHASE 6: MULTI-TIMEFRAME CHECKS ======================
    def _check_timeframe(self, clean: str, lines: List[str], issues: List[Issue]):
        has_set = bool(re.search(r'\bTimeFrameSet\s*\(', clean))
        has_expand = bool(re.search(r'\bTimeFrameExpand\s*\(', clean))
        has_restore = bool(re.search(r'\bTimeFrameRestore\s*\(', clean))

        if has_set:
            if not has_restore:
                ln = self._find_line_re(lines, r'TimeFrameSet\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "TimeFrame", "TimeFrameSet() used without TimeFrameRestore()",
                    "Add TimeFrameRestore() after calculations"))
            if not has_expand:
                ln = self._find_line_re(lines, r'TimeFrameSet\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "TimeFrame", "TimeFrameSet() used without TimeFrameExpand() — data won't align",
                    "Expand all variables: var = TimeFrameExpand(var, inWeekly)"))
        for m in re.finditer(r'TimeFrameExpand\s*\([^,]+,\s*(in\w+)\s*\)', clean):
            tf = m.group(1)
            if tf not in TIMEFRAME_CONSTANTS:
                ln = self._find_line_re(lines, r'TimeFrameExpand\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "TimeFrame", f"Invalid timeframe constant '{tf}' in TimeFrameExpand()",
                    "Use inDaily, inWeekly, inMonthly, etc."))
        for m in re.finditer(r'TimeFrameCompress\s*\(\s*(\d+)\s*\)', clean):
            n = int(m.group(1))
            if n <= 0:
                ln = self._find_line_re(lines, r'TimeFrameCompress\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "TimeFrame", "[ERROR_48] N-volume bar compression must be positive",
                    "Use positive value: TimeFrameCompress(10)"))

    # ====================== PHASE 7: BACKTEST AND TRADING CHECKS ======================
    def _check_backtest_signals(self, clean: str, lines: List[str], issues: List[Issue]):
        has_buy = bool(re.search(r'\bBuy\s*=', clean))
        has_sell = bool(re.search(r'\bSell\s*=', clean))
        has_short = bool(re.search(r'\bShort\s*=', clean))
        has_cover = bool(re.search(r'\bCover\s*=', clean))
        is_rotational = bool(re.search(r'\bEnableRotationalTrading\b', clean))

        if not is_rotational:
            if not has_buy:
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Backtest", "[ERROR_701] Missing Buy variable assignment",
                    "Add: Buy = Cross(MA(C,5), MA(C,20));"))
            if not has_sell:
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Backtest", "[ERROR_701] Missing Sell variable assignment",
                    "Add: Sell = Cross(MA(C,20), MA(C,5));"))
            if has_short and not has_cover:
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Backtest", "[ERROR_702] Short defined but Cover is missing",
                    "Add: Cover = Cross(C, MA(C,50));"))
            if has_cover and not has_short:
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Backtest", "[ERROR_702] Cover defined but Short is missing",
                    "Add: Short = Cross(MA(C,50), C);"))
        else:
            if has_buy or has_sell or has_short or has_cover:
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Backtest", "[ERROR_704] Cannot use Buy/Sell/Short/Cover in Rotational mode",
                    "Remove signal assignments or remove EnableRotationalTrading()"))

    def _check_rotational_trading(self, clean: str, lines: List[str], issues: List[Issue]):
        if re.search(r'\bEnableRotationalTrading\b', clean):
            if not re.search(r'\bPositionScore\s*=', clean):
                issues.append(Issue(1, 0, Severity.ERROR,
                    "Rotational", "[ERROR_703] Rotational trading requires PositionScore",
                    "Add: PositionScore = 50 - RSI(14);"))
        has_hold = bool(re.search(r'SetOption\s*\(\s*"HoldMinBars"', clean))
        has_samebar = bool(re.search(r'SetOption\s*\(\s*"AllowSameBarExit"', clean))
        if has_hold and has_samebar:
            ln = self._find_line(lines, "HoldMinBars")
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Backtest", "[ERROR_705] HoldMinBars conflicts with AllowSameBarExit",
                "Use one or the other, not both"))

    def _check_applystop(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'ApplyStop\s*\([^)]*IIf\s*\(', clean):
            ln = self._find_line_re(lines, r'ApplyStop\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Backtest", "[ERROR_4] ApplyStop type/mode parameters must be numbers, not arrays",
                "Use scalar values: ApplyStop(stopTypeLoss, stopModePercent, 5)"))
        for m in re.finditer(r'\bif\s*\([^)]*\)\s*ApplyStop', clean):
            ln = self._find_line_re(lines, r'ApplyStop\s*\(')
            issues.append(Issue(ln, 0, Severity.WARNING,
                "Backtest", "ApplyStop() should not be called conditionally — it is global",
                "Move ApplyStop() outside if/else blocks"))
        if re.search(r'\bEnableRotationalTrading\b', clean):
            for m in re.finditer(r'ApplyStop\s*\([^,]+,[^,]+,\s*([A-Za-z_]\w*)\s*[,)]', clean):
                stop_var = m.group(1)
                if stop_var not in {"True", "False", "Null", "stopTypeLoss", "stopTypeProfit",
                    "stopTypeTrailing", "stopModePoint", "stopModePercent"}:
                    ln = self._find_line_re(lines, r'ApplyStop\s*\(')
                    issues.append(Issue(ln, 0, Severity.ERROR,
                        "Rotational", "[ERROR_43] Variable stops not supported in Rotational mode",
                        "Use fixed stop values in rotational trading"))

    def _check_setoption_fields(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'SetOption\s*\(\s*"([^"]+)"', clean):
            field = m.group(1)
            if field not in VALID_SETOPTION_FIELDS:
                ln = self._find_line(lines, field)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Backtest", f"[ERROR_37] Unsupported SetOption field '{field}'",
                    "Check valid SetOption field names"))
        for m in re.finditer(r'GetOption\s*\(\s*"([^"]+)"', clean):
            field = m.group(1)
            if field not in VALID_GETOPTION_FIELDS:
                ln = self._find_line(lines, field)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Backtest", f"[ERROR_38] Unsupported GetOption field '{field}'",
                    "Check valid GetOption field names"))

    def _check_position_sizing(self, clean: str, lines: List[str], issues: List[Issue]):
        has_sps = bool(re.search(r'spsShares|spsPercentOfEquity|spsValue|spsNoChange', clean))
        has_setpos = bool(re.search(r'\bSetPositionSize\s*\(', clean))
        if has_sps and not has_setpos:
            issues.append(Issue(1, 0, Severity.WARNING,
                "Backtest", "Position sizing constants used but SetPositionSize() not called",
                "Add: SetPositionSize(10, spsPercentOfEquity)"))
        has_pos_size = bool(re.search(r'\bPositionSize\s*=', clean))
        has_setpos_size = bool(re.search(r'\bSetPositionSize\s*\(', clean))
        if not has_pos_size and not has_setpos_size:
            issues.append(Issue(1, 0, Severity.WARNING,
                "Backtest", "No PositionSize or SetPositionSize defined — using default sizing",
                "Add PositionSize = -10 or SetPositionSize(10, spsPercentOfEquity)"))

    # ====================== PHASE 8: OPTIMIZATION CHECKS ======================
    def _check_optimization(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'Optimize\s*\(\s*"([^"]*)"\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)', clean):
            name = m.group(1)
            min_val = m.group(3).strip()
            max_val = m.group(4).strip()
            step = m.group(5).strip()
            ln = self._find_line_re(lines, r'Optimize\s*\(')
            if not name:
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Optimization", "[ERROR_49] Optimization parameter name must not be empty",
                    "Give a name: Optimize(\"Period\", 10, 5, 20, 1)"))
            try:
                mn = float(min_val)
                mx = float(max_val)
                if mn > mx:
                    issues.append(Issue(ln, 0, Severity.ERROR,
                        "Optimization", f"[ERROR_50] Optimize minimum ({mn}) > maximum ({mx})",
                        "Ensure min <= max"))
            except ValueError:
                pass
            try:
                s = float(step)
                if s <= 0:
                    issues.append(Issue(ln, 0, Severity.ERROR,
                        "Optimization", f"[ERROR_50] Optimize step ({s}) must be > 0",
                        "Use positive step value"))
            except ValueError:
                pass
        if re.search(r'\bOptimizerSetOption\s*\(', clean):
            # Note: house default is the Tribes ("trib") optimiser engine.
            if not re.search(r'\bOptimizerSetEngine\s*\(', clean):
                ln = self._find_line_re(lines, r'OptimizerSetOption\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Optimization", "[ERROR_94] Must call OptimizerSetEngine() before OptimizerSetOption()",
                    "Add: OptimizerSetEngine(\"trib\");"))
        for m in re.finditer(r'Optimize\s*\(\s*"([^"]+)"\s*,', clean):
            name = m.group(1)
            if not re.search(rf'Param\s*\(\s*"{re.escape(name)}"', clean):
                ln = self._find_line(lines, name)
                issues.append(Issue(ln, 0, Severity.SUGGESTION,
                    "Optimization", f"Optimize(\"{name}\") without matching Param() — consider Param+Optimize pattern",
                    f"Add: {name}_Dflt = Param(\"{name}\", default, min, max, step);"))

    # ====================== PHASE 9: FILE I/O CHECKS ======================
    def _check_file_io(self, clean: str, lines: List[str], issues: List[Issue]):
        has_fopen = bool(re.search(r'\bfopen\s*\(', clean))
        has_fclose = bool(re.search(r'\bfclose\s*\(', clean))
        if has_fopen and not has_fclose:
            ln = self._find_line_re(lines, r'fopen\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "File I/O", "[ERROR_53] fopen() called without fclose() — files left open",
                "Always call fclose(fh) after fopen()"))
        for m in re.finditer(r'fclose\s*\(\s*([A-Za-z_]\w*)\s*\)', clean):
            var_name = m.group(1)
            if not re.search(rf'if\s*\(\s*{re.escape(var_name)}\s*\)', clean):
                ln = self._find_line_re(lines, r'fclose\s*\(')
                issues.append(Issue(ln, 0, Severity.WARNING,
                    "File I/O", f"[ERROR_26] fclose({var_name}) without checking file handle — may be NULL",
                    f"Add: if({var_name}) {{ fclose({var_name}); }}"))
        for func in ["fputs", "fgets"]:
            for m in re.finditer(rf'\b{func}\s*\([^,]+,\s*([A-Za-z_]\w*)\s*\)', clean):
                var_name = m.group(1)
                if var_name not in ALL_FUNCTIONS and not re.search(rf'if\s*\(\s*{re.escape(var_name)}\s*\)', clean):
                    ln = self._find_line_re(lines, rf'{func}\s*\(')
                    issues.append(Issue(ln, 0, Severity.WARNING,
                        "File I/O", f"[ERROR_26] {func}() without checking file handle",
                        f"Add: if({var_name}) {{ {func}(...); }}"))

    # ====================== PHASE 10: OLE/COM CHECKS ======================
    def _check_ole_warnings(self, clean: str, lines: List[str], issues: List[Issue]):
        if re.search(r'\bCreateObject\b|\bCreateStaticObject\b', clean):
            ln = self._find_line_re(lines, r'Create(?:Static)?Object')
            issues.append(Issue(ln, 0, Severity.WARNING,
                "OLE/COM", "[WARNING_503] Using OLE/CreateObject is slow in multi-threaded apps",
                "Replace with native AFL commands if possible"))

    # ====================== PHASE 11: PLOT AND EFFICIENCY CHECKS ======================
    def _check_plot_efficiency(self, clean: str, lines: List[str], issues: List[Issue]):
        plot_count = len(re.findall(r'\bPlot\s*\(', clean)) + len(re.findall(r'\bPlotOHLC\s*\(', clean))
        if plot_count > 500:
            issues.append(Issue(1, 0, Severity.WARNING,
                "Plot", f"[WARNING_502] Plot()/PlotOHLC() called {plot_count} times (>500 is inefficient)",
                "Combine LineArrays into single Plot() call"))
        for m in re.finditer(r'Plot\s*\(\s*[^,]+,\s*"[^"]*"\s*,\s*color\w+\s*\)', clean):
            ln = self._find_line_re(lines, r'Plot\s*\(')
            issues.append(Issue(ln, 0, Severity.SUGGESTION,
                "Plot", "Plot() called without style argument — using default style",
                "Add style: Plot(arr, \"Name\", colorGreen, styleLine)"))

    def _check_exrem(self, clean: str, lines: List[str], issues: List[Issue]):
        has_buy = bool(re.search(r'\bBuy\s*=\s*Cross\s*\(', clean))
        has_sell = bool(re.search(r'\bSell\s*=', clean))
        has_exrem = bool(re.search(r'\bExRem\s*\(', clean))
        if (has_buy or has_sell) and not has_exrem:
            ln = self._find_line(lines, "Buy =") if has_buy else self._find_line(lines, "Sell =")
            issues.append(Issue(ln if ln else 1, 0, Severity.SUGGESTION,
                "Signal", "Consider using ExRem(Buy, Sell) to prevent consecutive duplicate signals",
                "Buy = ExRem(Cross(MA(C,5), MA(C,20)), Sell);"))

    # ====================== PHASE 12: MATRIX CHECKS ======================
    def _check_matrix(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'\bMatrix\s*\(([^)]*)\)', clean):
            args_str = m.group(1)
            arg_count = self._count_args(args_str)
            if arg_count < 3:
                ln = self._find_line_re(lines, r'Matrix\s*\(')
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Matrix", "Matrix() requires 3 arguments: rows, cols, initValue",
                    "Matrix(10, 10, 0)"))

    # ====================== PHASE 13: CASCADING ERROR DETECTION ======================
    def _detect_cascading_errors(self, issues: List[Issue], clean: str, lines: List[str]):
        for pattern_name, pattern_info in CASCADE_PATTERNS.items():
            trigger_codes = set(pattern_info["triggers"])
            def _safe_code(issue):
                try:
                    if issue.error_code:
                        cleaned = issue.error_code.replace("E","").replace("W","").replace("[","").replace("]","")
                        match = re.match(r'(\d+)', cleaned)
                        return int(match.group(1)) if match else None
                except (ValueError, AttributeError):
                    return None
                return None
            trigger_issues = [i for i in issues if _safe_code(i) in trigger_codes]
            for trigger in trigger_issues:
                for other in issues:
                    if other != trigger and abs(other.line - trigger.line) <= 5:
                        if other not in trigger_issues:
                            other.cascading = True
                            other.cascading_parent = trigger.line
                            if "Cascading" not in other.category:
                                other.category = f"Cascading (caused by line {trigger.line})"

        bracket_errors = [i for i in issues if i.category == "Bracket" and i.severity == Severity.ERROR]
        if bracket_errors:
            for other in issues:
                if other.category not in ("Bracket", "Cascading") and other.severity == Severity.ERROR:
                    if not other.cascading:
                        for be in bracket_errors:
                            if abs(other.line - be.line) <= 10:
                                other.cascading = True
                                other.cascading_parent = be.line
                                other.category = f"Cascading (may be caused by bracket error at line {be.line})"
                                break

        for i, issue in enumerate(issues):
            if "missing semicolon" in issue.message.lower() or "ERROR_32" in issue.message:
                for other in issues:
                    if other != issue and other.line > issue.line and other.line <= issue.line + 3:
                        if other.severity == Severity.ERROR and not other.cascading:
                            other.cascading = True
                            other.cascading_parent = issue.line
                            other.category = f"Cascading (caused by missing semicolon at line {issue.line})"

    # ====================== PHASE 14: SHADOWING CHECKS ======================
    def _check_shadowing(self, clean: str, lines: List[str], issues: List[Issue]):
        clean_lower = clean.lower()
        all_funcs_lower = {f.lower(): f for f in ALL_FUNCTIONS}
        
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*=[^=]', clean_lower):
            var_lower = m.group(1)
            if var_lower in all_funcs_lower:
                original_func = all_funcs_lower[var_lower]
                if original_func not in SIGNAL_OUTPUTS and original_func not in {"MA", "EMA", "RSI", "MACD"}:
                    for i, line in enumerate(lines, 1):
                        if re.search(rf'\b{re.escape(var_lower)}\s*=', line.lower()):
                            issues.append(Issue(i, 0, Severity.WARNING,
                                "Shadow", f"Variable '{var_lower}' (case-insensitive) shadows built-in function '{original_func}'",
                                f"Use '{original_func}Val' or '{original_func.lower()}Period' instead"))
                            break
        
        for m in re.finditer(r'\bfunction\s+([A-Za-z_]\w*)\s*\(', clean_lower):
            fname_lower = m.group(1)
            if fname_lower in all_funcs_lower:
                original_func = all_funcs_lower[fname_lower]
                for i, line in enumerate(lines, 1):
                    if re.search(rf'\bfunction\s+{re.escape(fname_lower)}\s*\(', line.lower()):
                        issues.append(Issue(i, 0, Severity.ERROR,
                            "Shadow", f"[ERROR_34] Cannot define function '{fname_lower}' — name conflicts with built-in '{original_func}'",
                            "Use a different function name"))
                        break

    # ====================== PHASE 15: PARAM/OPTIMIZE PATTERN CHECKS ======================
    def _check_param_patterns(self, clean: str, lines: List[str], issues: List[Issue]):
        params = {}
        for m in re.finditer(r'Param\s*\(\s*"([^"]+)"\s*,\s*([^,]+)', clean):
            params[m.group(1)] = m.group(2).strip()
        optimizes = {}
        for m in re.finditer(r'Optimize\s*\(\s*"([^"]+)"\s*,\s*([^,]+)', clean):
            optimizes[m.group(1)] = m.group(2).strip()
        for name, default in optimizes.items():
            if name in params:
                if params[name] != default:
                    ln = self._find_line(lines, name)
                    issues.append(Issue(ln, 0, Severity.SUGGESTION,
                        "Param", f"Optimize(\"{name}\") default ({default}) doesn't match Param() default ({params[name]})",
                        "Make Optimize default match Param default"))
        for func, hint in TWO_ARG_FUNCTIONS.items():
            pattern = rf'\b{func}\s*\(\s*[^,]+\s*,\s*(\d+)\s*\)'
            for m in re.finditer(pattern, clean):
                period = int(m.group(1))
                if period > 1:
                    ln = self._find_line_re(lines, rf'{func}\s*\(')
                    issues.append(Issue(ln, 0, Severity.SUGGESTION,
                        "Param", f"Hardcoded period {period} in {func}() — consider using Param()",
                        f"period = Param(\"{func} Period\", {period}, 2, 100, 1);"))

    # ====================== PHASE 16: STRING CHECKS ======================
    def _check_string_operations(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'"[^"]*"\s*[\-*/^%]', clean):
            ln = self._find_line(lines, '"')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "String", "[ERROR_1] Cannot use arithmetic operators with strings",
                "Use numeric values only"))
        for m in re.finditer(r'WriteIf\s*\([^,]+,\s*(\d+)\s*,\s*(\d+)\s*\)', clean):
            ln = self._find_line_re(lines, r'WriteIf\s*\(')
            issues.append(Issue(ln, 0, Severity.SUGGESTION,
                "Function", "WriteIf() used with numeric values — consider IIf() for array output",
                "Use IIf() if you need array output, WriteIf() for single string"))

    # ====================== PHASE 17: GETRTDATA CHECKS ======================
    def _check_getrtdata(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'GetRTData\s*\(\s*"([^"]+)"', clean):
            field = m.group(1)
            if field not in VALID_GETRTDATA_FIELDS:
                ln = self._find_line(lines, field)
                issues.append(Issue(ln, 0, Severity.ERROR,
                    "Function", f"[ERROR_41] Unsupported GetRTData field '{field}'",
                    "Use valid RT data fields: Last, Change, Open, High, Low, Volume, etc."))
        if re.search(r'\bGetRTData\s*\(', clean):
            ln = self._find_line_re(lines, r'GetRTData\s*\(')
            issues.append(Issue(ln, 0, Severity.INFO,
                "Function", "GetRTData() requires Professional edition with running RT data source",
                "Returns Null silently in Standard edition"))

    # ====================== PHASE 18: CATEGORY CHECKS ======================
    def _check_category_functions(self, clean: str, lines: List[str], issues: List[Issue]):
        for m in re.finditer(r'CategoryAddSymbol\s*\([^,]+,\s*categorySector', clean):
            ln = self._find_line_re(lines, r'CategoryAddSymbol\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Category", "[ERROR_39] Cannot add symbol to sector — use categoryIndustry instead",
                "CategoryAddSymbol(\"\", categoryIndustry, 2)"))
        for m in re.finditer(r'CategoryRemoveSymbol\s*\([^,]+,\s*categorySector', clean):
            ln = self._find_line_re(lines, r'CategoryRemoveSymbol\s*\(')
            issues.append(Issue(ln, 0, Severity.ERROR,
                "Category", "[ERROR_40] Cannot remove symbol from sector — use categoryIndustry instead",
                "CategoryRemoveSymbol(\"\", categoryIndustry, 2)"))

    # ====================== PHASE 19: FUNCTION ARGUMENT TYPE CHECKS ======================
    def _check_function_arg_types(self, clean: str, lines: List[str], issues: List[Issue]):
        for func_name, sig in {**MULTI_ARG_FUNCTIONS, **PLOT_FUNCTIONS, **PARAM_FUNCTIONS, **EXPLORATION_FUNCTIONS}.items():
            min_args, hint = sig
            pattern = rf'\b{re.escape(func_name)}\s*\('
            for m in re.finditer(pattern, clean):
                start = m.end()
                depth = 1
                end = start
                while end < len(clean) and depth > 0:
                    if clean[end] == '(':
                        depth += 1
                    elif clean[end] == ')':
                        depth -= 1
                    end += 1
                if depth != 0:
                    continue
                
                args_str = clean[start:end-1].strip()
                if not args_str:
                    continue
                
                args = []
                current = ""
                depth = 0
                for ch in args_str:
                    if ch == '(':
                        depth += 1
                        current += ch
                    elif ch == ')':
                        depth -= 1
                        current += ch
                    elif ch == ',' and depth == 0:
                        args.append(current.strip())
                        current = ""
                    else:
                        current += ch
                if current.strip():
                    args.append(current.strip())

                for i, arg in enumerate(args):
                    arg_stripped = arg.strip()
                    is_string = bool(re.match(r'^"[^"]*"$', arg_stripped))
                    is_number = bool(re.match(r'^-?\d+(\.\d+)?$', arg_stripped))
                    
                    if func_name == "AddColumn" and i == 2 and is_string:
                        ln = self._find_line_re(lines, rf'{re.escape(func_name)}\s*\(')
                        issues.append(Issue(ln, 0, Severity.ERROR,
                            "Function", f"[ERROR_22] AddColumn format parameter must be a number, not a string",
                            "Use numeric format like 1.2, not \"1.2\""))
                    if func_name == "Foreign" and i == 1 and is_number:
                        ln = self._find_line_re(lines, rf'{re.escape(func_name)}\s*\(')
                        issues.append(Issue(ln, 0, Severity.ERROR,
                            "Function", f"[ERROR_5] Foreign() field must be a string like \"Close\", not a number",
                            "Use Foreign(\"SYMBOL\", \"Close\")"))


# ====================== CONVENIENCE FUNCTIONS ======================
def validate_afl_code(code: str) -> Dict[str, Any]:
    """Validate AFL code and return structured result as dict."""
    validator = AFLValidator()
    result = validator.validate(code)
    return result.to_dict()

def validate_afl_file(filepath: str) -> Dict[str, Any]:
    """Validate an AFL file and return structured result."""
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    return validate_afl_code(code)

def get_valid_colors() -> List[str]:
    return sorted(list(VALID_COLORS))

def get_valid_styles() -> List[str]:
    return sorted(list(VALID_PLOT_STYLES))

def get_valid_shapes() -> List[str]:
    return sorted(list(VALID_SHAPE_CONSTANTS))

def get_error_reference(error_code: int) -> Optional[Dict[str, str]]:
    """Get error reference by code number."""
    return ERROR_CODES.get(error_code)

def get_all_error_codes() -> List[int]:
    """Get list of all known error codes."""
    return sorted(ERROR_CODES.keys())


# ====================== MAIN ENTRY POINT ======================
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        result = validate_afl_file(filepath)
        print(f"Validation Result: {'PASS' if result['is_valid'] else 'FAIL'}")
        print(f"Errors: {result['error_count']}, Warnings: {result['warning_count']}, "
              f"Info: {result['info_count']}, Suggestions: {result['suggestion_count']}")
        print(f"Cascading issues: {result['cascade_count']}")
        print(f"\n--- Issues ---")
        for issue in result['issues']:
            cascade_mark = " [CASCADING]" if issue['cascading'] else ""
            print(f"  L{issue['line']:>4} [{issue['severity']:>8}] [{issue['category']}] {issue['message']}{cascade_mark}")
            if issue['suggestion']:
                print(f"         Suggestion: {issue['suggestion']}")
    else:
        print("Usage: python afl_validator.py <afl_file>")
        print("  Or import as module: from afl_validator import validate_afl_code")