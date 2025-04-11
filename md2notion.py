import mistletoe
import mistletoe.block_token as b
import mistletoe.span_token as s


def make_block(type_name: str, data: dict | None = None, **kwargs):
    return [{"object": "block", "type": type_name, type_name: data or {}, **kwargs}]


def spans2text(spans: list[s.SpanToken]):
    rich_text = []
    images = []
    for span in spans:
        children = []
        child_images = []
        if isinstance(span, s.Image):
            child_images = make_block(
                "image",
                {
                    "type": "external",
                    "external": {
                        "url": span.src,
                    },
                },
            )
        else:
            if hasattr(span, "children") and span.children:
                children, child_images = spans2text(span.children)
            else:
                children = [
                    {
                        "type": "text",
                        "text": {
                            "content": span.content,
                        },
                        "annotations": {},
                        "plain_text": span.content,
                    }
                ]
            # Handle style
            if isinstance(span, s.Strong):
                for c in children:
                    c["annotations"]["bold"] = True
            elif isinstance(span, s.Emphasis):
                for c in children:
                    c["annotations"]["italic"] = True
            elif isinstance(span, s.InlineCode):
                for c in children:
                    c["annotations"]["code"] = True
            elif isinstance(span, s.Strikethrough):
                for c in children:
                    c["annotations"]["strikethrough"] = True
            # Handle links
            if isinstance(span, (s.AutoLink, s.Link)):
                for c in children:
                    c["text"]["link"] = {"url": span.target}
                    c["href"] = span.target
        rich_text += children
        images += child_images
    return rich_text, images


def heading2notion(block: b.Heading):
    text, images = spans2text(block.children)
    return (
        make_block(
            f"heading_{block.level}",
            {"rich_text": text},
        )
        + images
    )


def quote2notion(block: b.Quote):
    text, images = spans2text(block.children)
    return (
        make_block(
            "quote",
            {"rich_text": text},
        )
        + images
    )


def paragraph2notion(block: b.Paragraph):
    text, images = spans2text(block.children)
    return (
        make_block(
            "paragraph",
            {"rich_text": text},
        )
        + images
    )


def blockcode2notion(block: b.BlockCode):
    text, images = spans2text(block.children)
    return (
        make_block(
            "code",
            {
                "rich_text": text,
                "language": block.language or None,
            },
        )
        + images
    )


def codefence2notion(block: b.CodeFence):
    text, images = spans2text(block.children)
    return (
        make_block(
            "code",
            {
                "rich_text": text,
                "language": block.language or None,
            },
        )
        + images
    )


def listitem2notion(block: b.ListItem, list_type="bulleted_list_item"):
    # First child is usually Paragraph
    # Subsequent child is usually List
    p_text, p_images = spans2text(block.children[0].children)
    data = {"rich_text": p_text}
    if len(block.children) > 1 and isinstance(block.children[1], b.List):
        data["children"] = p_images + list2notion(block.children[1])
    return make_block(
        list_type,
        data,
    )


def list2notion(block: b.List):
    items = []
    for child in block.children:
        items += listitem2notion(
            child,
            list_type="numbered_list_item" if block.start else "bulleted_list_item",
        )
    return items


def tablerow2notion(block: b.TableRow):
    # Note Notion table does not support inline images
    return make_block(
        "table_row", {"cells": [spans2text(c.children)[0] for c in block.children]}
    )


def table2notion(block: b.Table):
    rows = tablerow2notion(block.header)
    table_width = max(
        len(block.header.children),
        *[len(row.children) for row in block.children],
    )
    for row in block.children:
        rows += tablerow2notion(row)
    return make_block(
        "table",
        {
            "table_width": table_width,
            "children": rows,
        },
    )


def break2notion(_: b.ThematicBreak):
    return make_block("divider")


def html2notion(block: b.HtmlBlock):
    # Encode in code block
    return blockcode2notion(block)


def md2notion(md: str):
    doc = mistletoe.Document(md)
    print(doc.children[-1].children)
    notion_blocks = []
    for child in doc.children:
        if isinstance(child, b.Heading):
            notion_blocks += heading2notion(child)
        elif isinstance(child, b.Quote):
            notion_blocks += quote2notion(child)
        elif isinstance(child, b.Paragraph):
            notion_blocks += paragraph2notion(child)
        elif isinstance(child, b.CodeFence):
            notion_blocks += codefence2notion(child)
        elif isinstance(child, b.BlockCode):
            notion_blocks += blockcode2notion(child)
        elif isinstance(child, b.List):
            notion_blocks += list2notion(child)
        elif isinstance(child, b.Table):
            notion_blocks += table2notion(child)
        elif isinstance(child, b.ThematicBreak):
            notion_blocks += break2notion(child)
        elif isinstance(child, b.HtmlBlock):
            notion_blocks += html2notion(child)
    return notion_blocks
