"""
Artifact Detection and Parsing for Chat Messages
Detects code artifacts (React, HTML, SVG, Mermaid) in AI responses
Optimized for streaming with open-ended patterns
"""

import re
from typing import Optional, Dict, List, Tuple
from enum import Enum


class ArtifactType(Enum):
    """Types of artifacts that can be rendered."""
    REACT = "react"
    HTML = "html"
    SVG = "svg"
    MERMAID = "mermaid"
    MARKDOWN = "markdown"
    CODE = "code"


class ArtifactParser:
    """Parse and detect artifacts in AI responses."""

    # Streaming-friendly patterns - match even if closing ``` is missing
    PATTERNS = {
        ArtifactType.REACT: [
            r'```(?:jsx|react)\n(.*?)(?:```|$)',  # Open-ended for streaming
            r'(?:import\s+React|from\s+["\']react["\'])',
            r'(?:export\s+default\s+function|const\s+\w+\s*=\s*\(\)\s*=>)',
        ],
        ArtifactType.HTML: [
            r'```html\n(.*?)(?:```|$)',  # Open-ended for streaming
            r'<!DOCTYPE\s+html>',
            r'<html[^>]*>',
        ],
        ArtifactType.SVG: [
            r'```svg\n(.*?)(?:```|$)',  # Open-ended for streaming
            r'<svg[^>]*>',
        ],
        ArtifactType.MERMAID: [
            r'```mermaid\n(.*?)(?:```|$)',  # Open-ended for streaming
        ],
        ArtifactType.MARKDOWN: [
            r'```(?:md|markdown)\n(.*?)(?:```|$)',  # Open-ended for streaming
        ],
    }

    @staticmethod
    def extract_artifacts(content: str) -> List[Dict]:
        """
        Extract all artifacts from content.
        Streaming-friendly: works with incomplete code blocks.

        Args:
            content: The message content to parse

        Returns:
            List of artifacts with type, code, and metadata
        """
        artifacts = []

        # Streaming-friendly pattern - matches even without closing ```
        code_blocks = re.finditer(r'```(\w*)\n(.*?)(?:```|$)', content, re.DOTALL)

        for match in code_blocks:
            language = match.group(1).lower() or 'code'
            code = match.group(2).strip()
            start_pos = match.start()
            end_pos = match.end()

            # Skip empty code blocks
            if not code:
                continue

            # Determine artifact type
            artifact_type = ArtifactParser._detect_artifact_type(language, code)

            if artifact_type:
                artifacts.append({
                    'type': artifact_type.value,
                    'language': language,
                    'code': code,
                    'start': start_pos,
                    'end': end_pos,
                    'id': f'artifact_{len(artifacts)}_{hash(code) % 10000}',
                    'complete': content[end_pos - 3:end_pos] == '```' if end_pos >= 3 else False
                })

        return artifacts

    @staticmethod
    def _detect_artifact_type(language: str, code: str) -> Optional[ArtifactType]:
        """Detect the type of artifact based on language and code content."""

        # Check explicit language tags first
        if language in ['jsx', 'react']:
            return ArtifactType.REACT
        elif language == 'html':
            return ArtifactType.HTML
        elif language == 'svg':
            return ArtifactType.SVG
        elif language == 'mermaid':
            return ArtifactType.MERMAID
        elif language in ['md', 'markdown']:
            return ArtifactType.MARKDOWN

        # Check code patterns for auto-detection
        if any(pattern in code for pattern in ['import React', 'from "react"', "from 'react'"]):
            return ArtifactType.REACT
        elif code.strip().startswith('<!DOCTYPE html>') or code.strip().startswith('<html'):
            return ArtifactType.HTML
        elif code.strip().startswith('<svg'):
            return ArtifactType.SVG
        elif any(keyword in code for keyword in
                 ['graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram']):
            return ArtifactType.MERMAID

        # Default to None if renderable type not detected
        return None

    @staticmethod
    def prepare_message_with_artifacts(content: str) -> Dict:
        """
        Prepare a message with separated text and artifacts.

        Args:
            content: The full message content

        Returns:
            Dict with 'text' and 'artifacts' keys
        """
        artifacts = ArtifactParser.extract_artifacts(content)

        # Remove artifact code blocks from text
        text = content
        for artifact in reversed(artifacts):  # Reverse to maintain indices
            # Add indicator text
            indicator = f"\n[Artifact: {artifact['type']}]\n"
            text = text[:artifact['start']] + indicator + text[artifact['end']:]

        return {
            'text': text.strip(),
            'artifacts': artifacts,
            'has_artifacts': len(artifacts) > 0
        }

    @staticmethod
    def wrap_react_for_preview(code: str) -> str:
        """
        Wrap React code for safe preview rendering.

        Args:
            code: Raw React/JSX code

        Returns:
            Complete HTML document ready for iframe rendering
        """
        # Clean up the code
        code = code.strip()

        # Check if it's a full component or just JSX
        has_export = 'export default' in code
        has_function = 'function' in code or '=>' in code

        if not has_export:
            # Wrap in a default export if needed
            if not has_function:
                code = f"export default function App() {{\n  return (\n{code}\n  );\n}}"
            else:
                code = f"export default {code}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        #root {{
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        {code}

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<App />);
    </script>
</body>
</html>"""

    @staticmethod
    def wrap_html_for_preview(code: str) -> str:
        """Wrap HTML code for safe preview."""
        code = code.strip()

        # If it's already a complete document, return as-is
        if code.startswith('<!DOCTYPE html>'):
            return code

        # Otherwise wrap it
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
    </style>
</head>
<body>
    {code}
</body>
</html>"""

    @staticmethod
    def wrap_svg_for_preview(code: str) -> str:
        """Wrap SVG code for safe preview."""
        code = code.strip()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        svg {{
            max-width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    {code}
</body>
</html>"""

    @staticmethod
    def wrap_mermaid_for_preview(code: str) -> str:
        """Wrap Mermaid code for rendering."""
        code = code.strip()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        .mermaid {{
            max-width: 100%;
        }}
    </style>
</head>
<body>
    <div class="mermaid">
{code}
    </div>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""