from ansi2html import Ansi2HTMLConverter

conv = Ansi2HTMLConverter(dark_bg=True, title="短剧视频反推剧本 — 对话记录 2026-03-31")

with open("2026-03-31-182520-local-command-caveatcaveat-the-messages-below-w.txt", "r", encoding="utf-8") as f:
    text = f.read()

html = conv.convert(text)
with open("conversation_ansi.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"Done: conversation_ansi.html")
