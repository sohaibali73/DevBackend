# Sandbox Test Prompts & Library Reference

---

## What's Built-In (No Installation Needed)

### Python — Available Immediately

These are pre-injected into `_SANDBOX_GLOBALS` the moment the server starts.  
Code can use them **without any `import` statement**.

| Name in sandbox | Package | Category |
|---|---|---|
| `math` | math | Standard library |
| `statistics` | statistics | Standard library |
| `json` | json | Standard library |
| `re` | re | Standard library |
| `csv` | csv | Standard library |
| `io`, `StringIO`, `BytesIO` | io | Standard library |
| `datetime`, `timedelta` | datetime | Standard library |
| `np`, `numpy` | numpy | Data science |
| `pd`, `pandas` | pandas | Data science |
| `scipy` | scipy | Data science |
| `plt`, `matplotlib` | matplotlib (Agg backend) | Plotting |
| `sns`, `seaborn` | seaborn | Plotting |
| `sympy` | sympy | Math |
| `plotly` | plotly | Interactive charts |
| `networkx` | networkx | Graph analysis |
| `sklearn` | scikit-learn | ML |
| `yf`, `yfinance` | yfinance | Finance |
| `edgartools` | edgartools | SEC / EDGAR |
| `httpx` | httpx | HTTP |
| `requests` | requests | HTTP |
| `aiohttp` | aiohttp | Async HTTP |
| `bs4`, `BeautifulSoup` | beautifulsoup4 | Web scraping |
| `lxml` | lxml | XML/HTML parsing |
| `pydantic` | pydantic | Validation |
| `rich` | rich | Terminal output |
| `tabulate` | tabulate | Tables |
| `tqdm` | tqdm | Progress bars |
| `pyarrow` | pyarrow | Arrow / Parquet |
| `openpyxl` | openpyxl | Excel |
| `Presentation`, `pptx` | python-pptx | PowerPoint |
| `jinja2` | jinja2 | Templating |
| `humanize` | humanize | Human-readable output |
| `orjson` | orjson | Fast JSON |
| `anthropic` | anthropic | Claude API |
| `Decimal`, `Fraction` | decimal / fractions | Precision math |
| `rank_bm25`, `rapidfuzz`, `textdistance` | search libs | Text/NLP |
| `tldextract`, `aiofiles` | misc | Utilities |
| `display`, `HTML`, `SVG`, `JSON` | built-in helpers | Jupyter-like output |

> **Important:** These are available as **globals** — no `import` needed. But if the code does `import numpy`, the AST validator will see it's not forbidden and allow it too (it's not on the blocked list).

### Python — Blocked Imports (AST Validated)

```
os  sys  subprocess  shutil  socket  pty  tty  fcntl  termios
ctypes  signal  resource  multiprocessing  pathlib  glob
importlib  builtins  inspect  gc  weakref  dis
```

Direct calls to `eval()`, `compile()`, `open()`, `exec()` are also blocked.

---

### React — CDN Packages (No Installation)

React components can import these directly — they load from `esm.sh` in the browser:

```
react                    react-dom              react-dom/client
lucide-react             @radix-ui/react-icons  react-icons
framer-motion            react-hook-form        react-router-dom
clsx                     tailwind-merge         class-variance-authority
@headlessui/react        @heroicons/react
date-fns                 dayjs                  moment
lodash                   lodash-es              ramda
mathjs                   uuid                   zod
axios                    immer                  zustand
jotai                    recoil                 classnames
recharts                 chart.js               d3
```

Tailwind CSS classes also work out of the box (CDN loaded).

---

### Can It Fetch External Libraries?

**Yes — three ways:**

| Method | How | Available after |
|---|---|---|
| Python pip install | `POST /sandbox/packages/install` with `language: "python"` | Immediately (injected into `_SANDBOX_GLOBALS` + `sys.path`) |
| JavaScript npm install | `POST /sandbox/packages/install` with `language: "javascript"` | Next Node.js execution |
| React CDN | Any `esm.sh`-resolvable package listed in the import map | Instantly at render time |

Installed Python packages persist in `~/.sandbox/python_venv/` and survive server restarts.

---

## Test Prompts

Use these with your chatbot. They cover all code paths.

> Tip: The first prompt in each multi-turn group **must use a fixed session_id** so variables carry over. In the chatbot, this is automatic via `sandbox_session_id` in the `conversations` table.

---

### Group 1 — Basic Python Execution

**Prompt 1.1 — Hello World**
```
Run this Python code and show me the output:
print("Hello from the sandbox!")
x = 2 ** 10
print(f"2^10 = {x}")
```
Expected: `Hello from the sandbox!` + `2^10 = 1024`

---

**Prompt 1.2 — Math & Standard Library**
```
Calculate the standard deviation, mean, and median of [14, 22, 5, 8, 31, 17, 9].
Use the built-in statistics module.
```
Expected: Numeric output with mean/median/stdev.

---

**Prompt 1.3 — Pandas DataFrame**
```
Create a pandas DataFrame with 5 rows of fake sales data (product name, quantity, price).
Calculate total revenue per product.
Print the result.
```
Expected: Formatted DataFrame table in output.

---

**Prompt 1.4 — NumPy Math**
```
Using numpy, generate 1000 random samples from a normal distribution with mean=50 and std=10.
Print the actual mean, std, min, and max of the sample.
```
Expected: Values close to 50, 10.

---

### Group 2 — Session Persistence (Multi-Turn)

**Prompt 2.1 — Turn 1**
```
Store the list [10, 20, 30, 40, 50] in a variable called my_data.
Also store the string "Alice" in user_name.
Confirm what's stored.
```
Expected: Confirmation that variables are saved.

---

**Prompt 2.2 — Turn 2 (same conversation)**
```
Now compute the sum and average of my_data.
Also greet the user using user_name.
```
Expected: Uses `my_data` and `user_name` from turn 1 — no redefinition needed.

---

**Prompt 2.3 — Turn 3**
```
Add 100 to each element of my_data using a list comprehension.
Store the result in scaled_data.
Print both lists.
```
Expected: Shows original list AND new scaled list. `my_data` persists.

---

### Group 3 — Matplotlib Charts

**Prompt 3.1 — Line Chart**
```
Plot a sine wave from 0 to 4π using matplotlib.
Use 500 points. Add a title "Sine Wave" and axis labels.
Show the plot.
```
Expected: `display_type: "image"`, base64 PNG artifact rendered as `<img>`.

---

**Prompt 3.2 — Bar Chart**
```
Create a bar chart showing monthly revenue:
Jan=12000, Feb=15000, Mar=9000, Apr=18000, May=22000, Jun=19000
Use matplotlib. Add value labels on top of each bar.
```
Expected: Image artifact with bar chart.

---

**Prompt 3.3 — Multi-figure (two plots)**
```
Create two matplotlib figures:
1. A histogram of 500 random normal values
2. A scatter plot of 100 random x,y points

Call plt.show() after each. Return both as images.
```
Expected: Two separate `image` artifacts in the response.

---

**Prompt 3.4 — Seaborn Heatmap**
```
Create a 10x10 correlation matrix of random data using seaborn as a heatmap.
Use a "coolwarm" color palette.
```
Expected: Image artifact.

---

### Group 4 — display() / HTML Helpers

**Prompt 4.1 — HTML Table**
```
Use the display(HTML(...)) helper to create an HTML table showing:
- Product: Apple, Banana, Cherry
- Price: $1.20, $0.50, $3.00
- In Stock: Yes, No, Yes

Style it with inline CSS — alternating row colors.
```
Expected: `display_type: "html"`, artifact with styled HTML table in iframe.

---

**Prompt 4.2 — SVG Drawing**
```
Use display(SVG(...)) to draw a simple bar chart as SVG.
Show 4 bars with different heights and colors.
Add labels below each bar.
```
Expected: `display_type: "image"`, SVG artifact.

---

**Prompt 4.3 — JSON Output**
```
Analyze this data and return it as a structured JSON artifact using display(JSON(...)):
{"q1": 1200, "q2": 1800, "q3": 1500, "q4": 2200}
Include calculated metrics: total, average, max_quarter, growth_rate.
```
Expected: `display_type: "json"`, JSON artifact rendered as formatted tree.

---

### Group 5 — React Components

**Prompt 5.1 — Counter Component**
```
Build a React counter component with:
- A number display starting at 0
- Increment (+) and Decrement (-) buttons
- A Reset button
- Tailwind styling
```
Expected: `display_type: "react"`, self-contained HTML in iframe with working buttons.

---

**Prompt 5.2 — Data Table with Filtering**
```
Build a React component showing a filterable table of 10 employees:
name, department, salary. Add a text input to filter by name.
Use Tailwind for styling.
```
Expected: Interactive table with live filter in iframe.

---

**Prompt 5.3 — Recharts Bar Chart**
```
Build a React component using recharts showing quarterly revenue:
Q1: 45000, Q2: 62000, Q3: 58000, Q4: 71000.
Include a tooltip and axis labels. Use a purple color scheme.
```
Expected: React artifact with a live interactive recharts bar chart.

---

**Prompt 5.4 — Dark Mode Toggle**
```
Build a React settings panel with:
- Dark/light mode toggle (switches background color)
- Font size slider (small/medium/large)
- A preview area showing text at the selected size/theme
Use framer-motion for smooth transitions. Tailwind styling.
```
Expected: Interactive React app with animations in iframe.

---

**Prompt 5.5 — Lucide Icons Dashboard**
```
Build a React dashboard card layout with 4 metric cards using lucide-react icons:
- Users: 1,234 (Users icon)
- Revenue: $45,678 (DollarSign icon)
- Orders: 89 (ShoppingCart icon)
- Conversion: 3.2% (TrendingUp icon)
Each card should have a colored icon, metric name, and value.
```
Expected: Grid of styled cards in iframe with lucide icons loaded from CDN.

---

### Group 6 — JavaScript Execution

**Prompt 6.1 — Basic JS**
```
Run this JavaScript code:
const nums = [1, 2, 3, 4, 5];
const doubled = nums.map(n => n * 2);
const sum = doubled.reduce((a, b) => a + b, 0);
console.log("Doubled:", doubled.join(", "));
console.log("Sum:", sum);
```
Expected: `language: "javascript"`, output with doubled array and sum.

---

**Prompt 6.2 — Lodash Usage**
```
Using lodash in JavaScript:
const data = [
  { name: "Alice", score: 85 },
  { name: "Bob", score: 92 },
  { name: "Carol", score: 78 },
  { name: "Dave", score: 95 }
];
Sort by score descending and log each person's rank and name.
```
Expected: Ranked list using lodash's `orderBy`.

---

### Group 7 — Package Installation

**Prompt 7.1 — Install a Python Package**
```
Install the Python package "faker" and use it to generate:
- 5 fake names
- 5 fake email addresses
- 5 fake US phone numbers
Print them in a formatted table using tabulate.
```
Expected: `POST /sandbox/packages/install` called first, then faker used.

---

**Prompt 7.2 — Check if Installed**
```
Check if the package "polars" is installed.
If not, install it and then create a polars DataFrame with 3 columns and 5 rows.
```
Expected: Checks package status, installs if missing, uses it.

---

### Group 8 — Financial Data

**Prompt 8.1 — Live Stock Data**
```
Fetch Apple (AAPL) stock data for the last 30 days using yfinance.
Calculate: starting price, ending price, percentage change, highest and lowest close.
Plot the closing price as a line chart.
```
Expected: Fetches live data + image artifact of price chart.

---

**Prompt 8.2 — Comparison Chart**
```
Compare AAPL, MSFT, and GOOGL stock performance over the last 60 days.
Normalize all three to 100 at the start date.
Plot them on the same chart with a legend.
```
Expected: Multi-line normalized comparison chart as image artifact.

---

### Group 9 — Security Tests (Should Be Blocked)

Use these to confirm the AST validator is working. The sandbox should **reject** these.

**Prompt 9.1 — Should be blocked**
```
Run: import os; print(os.listdir('/'))
```
Expected: `success: false`, error contains "Forbidden import: os"

---

**Prompt 9.2 — Should be blocked**
```
Run: import subprocess; subprocess.run(['ls', '-la'])
```
Expected: `success: false`, error contains "Forbidden import: subprocess"

---

**Prompt 9.3 — Should be blocked**
```
Run: eval("__import__('os').system('whoami')")
```
Expected: `success: false`, error contains "Forbidden call: eval()"

---

**Prompt 9.4 — open() blocked**
```
Run: f = open('/etc/passwd', 'r'); print(f.read())
```
Expected: `success: false`, error contains "Forbidden call: open()"

---

**Prompt 9.5 — Bypass attempt (should still be blocked)**
```
Run: __import__('os').environ
```
Expected: `success: false`, error contains "Forbidden import via __import__: os"

---

### Group 10 — Edge Cases & Stress Tests

**Prompt 10.1 — Large output**
```
Generate a 20x20 multiplication table and print it formatted with aligned columns.
```
Expected: Large text output captured correctly.

---

**Prompt 10.2 — Timeout handling**
```
Run a loop that counts to 1 billion.
```
Expected: `success: false`, error contains "timed out"

---

**Prompt 10.3 — Multiple artifacts in one run**
```
Create 3 different matplotlib plots:
1. A pie chart of market share (Apple 30%, Samsung 25%, Other 45%)
2. A line chart of temperature over 24 hours
3. A scatter plot of random data

Call plt.show() after each. Show all 3 charts.
```
Expected: Three separate `image` artifacts in the response.

---

**Prompt 10.4 — Mixed output + artifact**
```
Create a pandas DataFrame of 10 random students with name, grade, and score.
Print the top 3 students.
Also plot a bar chart of all scores sorted descending.
```
Expected: Text output (top 3) AND image artifact (bar chart) in the same response.

---

**Prompt 10.5 — Session + chart**
```
[Turn 1] Store this data: prices = {"AAPL": 189.5, "TSLA": 245.2, "NVDA": 875.0}
[Turn 2] Plot the stored prices as a horizontal bar chart using matplotlib.
```
Expected: Turn 2 uses `prices` from turn 1 and produces an image artifact.

---

## Summary: What Needs Installation vs What's Free

```
✅ FREE (pre-injected at startup):
   numpy, pandas, matplotlib, seaborn, scipy, sympy, plotly,
   networkx, scikit-learn, yfinance, edgartools, requests, httpx,
   aiohttp, beautifulsoup4, pydantic, rich, tabulate, openpyxl,
   python-pptx, jinja2, orjson, and more…

✅ FREE for React (CDN at render time):
   react, lucide-react, recharts, chart.js, d3, zustand, framer-motion,
   lodash, zod, date-fns, tailwind, and more…

📦 NEEDS INSTALL (POST /sandbox/packages/install):
   polars, statsmodels, faker, transformers, nltk, spacy,
   geopandas, xgboost, lightgbm, catboost, altair, bokeh,
   or any other PyPI package not in the preinstalled list
```
