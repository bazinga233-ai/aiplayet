"""将 Claude Code 对话导出文件转换为美观的 HTML"""
import re
import html as html_lib

INPUT_FILE = r"D:\project\others\novalai\2026-03-31-182520-local-command-caveatcaveat-the-messages-below-w.txt"
OUTPUT_FILE = r"D:\project\others\novalai\conversation.html"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    raw = f.read()

# 跳过开头的欢迎框
lines = raw.split("\n")
start_idx = 0
for i, line in enumerate(lines):
    if line.startswith("> ") or line.startswith("● "):
        start_idx = i
        break

# 解析消息块
blocks = []
current = None

def flush():
    global current
    if current:
        blocks.append(current)
        current = None

for line in lines[start_idx:]:
    stripped = line.rstrip()

    if stripped.startswith("> "):
        flush()
        current = {"type": "user", "lines": [stripped[2:]]}
    elif stripped.startswith("● "):
        flush()
        current = {"type": "ai", "lines": [stripped[2:]]}
    elif stripped.startswith("✻ "):
        flush()
        blocks.append({"type": "meta", "lines": [stripped[2:]]})
    elif current:
        current["lines"].append(stripped)
    # 忽略欢迎框等无归属行

flush()

def escape(text):
    return html_lib.escape(text)

def parse_table(lines_block):
    """解析 ASCII 表格为 HTML table"""
    rows = []
    for l in lines_block:
        l = l.strip()
        if l.startswith("├") or l.startswith("┌") or l.startswith("└"):
            continue
        if l.startswith("│"):
            cells = [c.strip() for c in l.split("│")[1:-1]]
            rows.append(cells)
    if not rows:
        return ""
    h = '<table class="data-table"><thead><tr>'
    for c in rows[0]:
        h += f"<th>{escape(c)}</th>"
    h += "</tr></thead><tbody>"
    for row in rows[1:]:
        h += "<tr>"
        for c in row:
            h += f"<td>{escape(c)}</td>"
        h += "</tr>"
    h += "</tbody></table>"
    return h

def render_content(lines_list):
    """将内容行渲染为 HTML"""
    result = []
    i = 0
    while i < len(lines_list):
        line = lines_list[i]
        stripped = line.strip()

        # 检测表格开始
        if stripped.startswith("┌"):
            table_lines = []
            while i < len(lines_list):
                tl = lines_list[i].strip()
                table_lines.append(tl)
                if tl.startswith("└"):
                    break
                i += 1
            result.append(parse_table(table_lines))
            i += 1
            continue

        # 工具调用
        tool_patterns = [
            r'^(Web Search|Bash|Read|Fetch|Searched for|Glob|Edit|Write)\b',
            r'^⎿',
            r'^Did \d+ search',
        ]
        is_tool = any(re.match(p, stripped) for p in tool_patterns)
        if is_tool:
            result.append(f'<div class="tool-call">{escape(stripped)}</div>')
            i += 1
            continue

        # 代码块（缩进的代码样式内容）
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines_list):
                if lines_list[i].strip().startswith("```"):
                    break
                code_lines.append(lines_list[i])
                i += 1
            code_text = escape("\n".join(code_lines))
            result.append(f'<pre class="code-block"><code>{code_text}</code></pre>')
            i += 1
            continue

        # 分隔线
        if stripped == "---":
            result.append("<hr>")
            i += 1
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 标题样式 (## 或 数字.)
        if stripped.startswith("## ") or stripped.startswith("### "):
            level = 3 if stripped.startswith("### ") else 2
            text = stripped.lstrip("#").strip()
            result.append(f'<h{level} class="section-title">{escape(text)}</h{level}>')
            i += 1
            continue

        # 列表项
        if stripped.startswith("- "):
            result.append(f'<div class="list-item">• {escape(stripped[2:])}</div>')
            i += 1
            continue

        if re.match(r'^\d+\.\s', stripped):
            result.append(f'<div class="list-item">{escape(stripped)}</div>')
            i += 1
            continue

        # 普通段落
        result.append(f'<p>{escape(stripped)}</p>')
        i += 1

    return "\n".join(result)

# 构建消息 HTML
messages_html = []
topic_anchors = []
topic_id = 0

for block in blocks:
    content = render_content(block["lines"])
    if not content.strip():
        continue

    if block["type"] == "user":
        topic_id += 1
        anchor = f"topic-{topic_id}"
        label = block["lines"][0][:40].strip()
        if label:
            topic_anchors.append((anchor, label))
        messages_html.append(f'''
        <div class="message user-message" id="{anchor}">
            <div class="message-label">👤 用户</div>
            <div class="message-content">{content}</div>
        </div>''')
    elif block["type"] == "ai":
        messages_html.append(f'''
        <div class="message ai-message">
            <div class="message-label">🤖 Claude</div>
            <div class="message-content">{content}</div>
        </div>''')
    elif block["type"] == "meta":
        messages_html.append(f'''
        <div class="meta-info">{escape(block["lines"][0])}</div>''')

# 目录 HTML
nav_html = ""
for anchor, label in topic_anchors:
    nav_html += f'<a href="#{anchor}" class="nav-item">{escape(label)}</a>\n'

# 完整 HTML
final_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>短剧视频反推剧本 — 技术方案与实现</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    line-height: 1.7;
}}
.header {{
    background: linear-gradient(135deg, #1a1b2e 0%, #16213e 50%, #0f3460 100%);
    padding: 40px 20px;
    text-align: center;
    border-bottom: 1px solid #30363d;
}}
.header h1 {{
    font-size: 28px;
    color: #58a6ff;
    margin-bottom: 8px;
}}
.header .subtitle {{
    color: #8b949e;
    font-size: 14px;
}}
.layout {{
    display: flex;
    max-width: 1200px;
    margin: 0 auto;
}}
.sidebar {{
    width: 260px;
    min-width: 260px;
    padding: 20px 16px;
    border-right: 1px solid #21262d;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    background: #0d1117;
}}
.sidebar h3 {{
    color: #58a6ff;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 12px;
}}
.nav-item {{
    display: block;
    padding: 6px 10px;
    color: #8b949e;
    text-decoration: none;
    font-size: 13px;
    border-radius: 6px;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.nav-item:hover {{
    background: #161b22;
    color: #c9d1d9;
}}
.main {{
    flex: 1;
    padding: 24px;
    min-width: 0;
}}
.message {{
    margin-bottom: 16px;
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid #21262d;
}}
.user-message {{
    background: #161b22;
    border-left: 3px solid #58a6ff;
}}
.ai-message {{
    background: #0d1117;
    border-left: 3px solid #3fb950;
}}
.message-label {{
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 8px;
    color: #8b949e;
}}
.message-content p {{
    margin-bottom: 8px;
}}
.message-content h2, .message-content h3 {{
    color: #58a6ff;
    margin: 16px 0 8px;
}}
.section-title {{
    color: #58a6ff;
}}
.data-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 14px;
}}
.data-table th {{
    background: #21262d;
    color: #58a6ff;
    padding: 10px 12px;
    text-align: left;
    border: 1px solid #30363d;
    font-weight: 600;
}}
.data-table td {{
    padding: 8px 12px;
    border: 1px solid #30363d;
}}
.data-table tbody tr:nth-child(even) {{
    background: #161b22;
}}
.data-table tbody tr:hover {{
    background: #1c2128;
}}
.tool-call {{
    background: #1c1c2e;
    color: #7c8aaa;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-family: "Fira Code", "Cascadia Code", monospace;
    margin: 4px 0;
    border-left: 2px solid #484f58;
}}
.code-block {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px 16px;
    overflow-x: auto;
    font-family: "Fira Code", "Cascadia Code", monospace;
    font-size: 13px;
    margin: 10px 0;
    color: #e6edf3;
}}
.list-item {{
    padding: 2px 0 2px 16px;
    color: #c9d1d9;
}}
.meta-info {{
    text-align: center;
    color: #484f58;
    font-size: 12px;
    padding: 4px 0;
    font-style: italic;
}}
hr {{
    border: none;
    border-top: 1px solid #21262d;
    margin: 16px 0;
}}
.footer {{
    text-align: center;
    padding: 30px;
    color: #484f58;
    font-size: 13px;
    border-top: 1px solid #21262d;
}}
.footer span {{
    color: #58a6ff;
}}
@media (max-width: 768px) {{
    .layout {{ flex-direction: column; }}
    .sidebar {{
        width: 100%;
        min-width: 100%;
        height: auto;
        position: relative;
        border-right: none;
        border-bottom: 1px solid #21262d;
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        padding: 12px;
    }}
    .sidebar h3 {{ width: 100%; }}
    .nav-item {{ font-size: 12px; padding: 4px 8px; }}
    .main {{ padding: 12px; }}
    .message {{ padding: 12px 14px; }}
}}
</style>
</head>
<body>
<div class="header">
    <h1>🎬 短剧视频反推剧本 — 技术方案与实现</h1>
    <div class="subtitle">Claude Code 对话记录 · 2026-03-31 · Qwen3.5-9B + FunASR</div>
</div>
<div class="layout">
    <nav class="sidebar">
        <h3>📑 对话目录</h3>
        {nav_html}
    </nav>
    <div class="main">
        {"".join(messages_html)}
    </div>
</div>
<div class="footer">
    Powered by <span>Claude Code</span> + <span>Qwen3.5-9B</span> + <span>FunASR</span>
</div>
</body>
</html>'''

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(final_html)

print(f"HTML generated: {OUTPUT_FILE}")
