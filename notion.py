import concurrent.futures as futures
import json
import os
from typing import TypedDict

import requests

from md2notion import md2notion

API_URL = "https://api.notion.com/v1"


class NotionSearchResult(TypedDict):
    id: str
    created_at: str
    modified_at: str
    title: str
    url: str
    public_url: str | None


def _get_post_title(post: dict):
    title_obj = post.get("properties", {}).get("title", {}).get("title", {})
    if isinstance(title_obj, list) and len(title_obj):
        return title_obj[0].get("plain_text")


def search_titles(query: str = "", num_results: int = 10) -> list[NotionSearchResult]:
    """
    Search Notion pages by titles

    Args:
    - query (str): Search query, defaults to empty string, which returns all accessible pages
    - num_results (int): Number of results, defaults to 10

    Returns:
        A list of pages sorted by last edited time, in descending order
        Each page is represented as a dictionary with the following attributes
        - id (str): Page ID
        - created_at (str): Creation timestamp
        - modified_at (str): Last modified timestamp
        - title (str): Page title
        - url (str): Page URL that requires authentication
        - public_url (str): Public page URL if page is published
    """
    page_size = min(num_results, 100)
    results = []
    start_cursor = None
    while len(results) < num_results:
        data = {
            "query": query,
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time",
            },
            "page_size": page_size,
        }
        if start_cursor:
            data["start_cursor"] = start_cursor
        response = requests.post(
            API_URL + "/search",
            headers={
                "Authorization": f"Bearer {os.environ['NOTION_INTEGRATION_SECRET']}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            },
            data=json.dumps(data),
        )
        response_json = response.json()
        results += [
            NotionSearchResult(
                id=r.get("id"),
                created_at=r.get("created_time"),
                modified_at=r.get("last_edited_time"),
                title=_get_post_title(r),
                url=r.get("url"),
                public_url=r.get("public_url"),
            )
            for r in response_json.get("results", [])
        ]
        if not response_json.get("has_more") or not response_json.get("next_cursor"):
            break
        start_cursor = response_json.get("next_cursor")
    return results[:num_results]


class NotionBlock(TypedDict):
    id: str
    created_at: str
    modified_at: str
    type: str
    data: str
    has_children: bool
    children: list["NotionBlock"]


def _get_block_children(block_id: str, num_blocks: int = 100):
    page_size = min(num_blocks, 100)
    blocks = []
    start_cursor = None
    while len(blocks) < num_blocks:
        url = API_URL + f"/blocks/{block_id}/children?page_size={page_size}"
        if start_cursor:
            url += f"&start_cursor={start_cursor}"
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {os.environ['NOTION_INTEGRATION_SECRET']}",
                "Notion-Version": "2022-06-28",
            },
        )
        response_json = response.json()
        with futures.ThreadPoolExecutor() as pool:
            new_blocks = pool.map(
                _dict_to_notion_block, response_json.get("results", [])
            )
        blocks += new_blocks
        if not response_json.get("has_more") or not response_json.get("next_cursor"):
            break
        start_cursor = response_json.get("next_cursor")
    return blocks


def _dict_to_notion_block(block_dict: dict) -> NotionBlock:
    block = NotionBlock(
        id=block_dict.get("id"),
        created_at=block_dict.get("created_time"),
        modified_at=block_dict.get("last_edited_time"),
        type=block_dict.get("type"),
        data=block_dict.get(block_dict.get("type"), None),
        has_children=block_dict.get("has_children", False),
        children=[],
    )
    if block_dict.get("has_children") and block_dict.get("type") != "child_page":
        block["children"] = _get_block_children(block_dict.get("id"))
    return block


def _rich_text_arr_to_text(arr: list[dict] | None) -> str:
    if arr is None:
        return ""
    texts = []
    for t in arr:
        text = t.get("plain_text", "")
        href = t.get("href")
        if href:
            texts.append(f"({text})[{href}]")
        else:
            texts.append(text)
    return "".join(texts)


def _format_children(block_dict: dict) -> str:
    text = ""
    if block_dict.get("has_children"):
        child_blocks = block_dict.get("children", [])
        for i, block in enumerate(child_blocks):
            block_text = _block_dict_to_text(block, i)
            text += "\n\t" + block_text.replace("\n", "\n\t")
    return text


def _block_dict_to_text(block_dict: dict, pos: int = 0) -> str:
    block_type = block_dict.get("type")
    data = block_dict.get("data", {})
    if block_type == "bookmark":
        caption = _rich_text_arr_to_text(data.get("caption"))
        url = data.get("url", "")
        return f"[{caption}]({url})"
    if block_type == "breadcrumb":
        return ""
    if block_type == "bulleted_list_item":
        text = "- " + _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "callout":
        return _rich_text_arr_to_text(data.get("rich_text"))
    if block_type == "child_database":
        return f"[{data.get('title')}](page_id={block_dict.get('id')})"
    if block_type == "child_page":
        return f"[{data.get('title')}](page_id={block_dict.get('id')})"
    if block_type == "code":
        return f"```{data.get('language')}\n{_rich_text_arr_to_text(data.get('rich_text'))}\n```"
    if block_type == "column_list":
        return _format_children(block_dict)
    if block_type == "divider":
        return "---"
    if block_type == "embed":
        url = data.get("url", "")
        return f"[{url}]({url})"
    if block_type == "equation":
        return data.get("expression", "")
    if block_type == "file":
        caption = _rich_text_arr_to_text(data.get("caption"))
        name = data.get("name")
        url = data.get("url", "")
        return f"[{caption or name or url}]({url})"
    if block_type.startswith("heading"):
        heading_size = int(block_type.replace("heading_", ""))
        text = _rich_text_arr_to_text(data.get("rich_text"))
        text = "#" * heading_size + f" {text}"
        return text + _format_children(block_dict)
    if block_type == "image":
        image_type = data.get("type")
        url = data.get(image_type, {}).get("url")
        return f"![{url}]({url})"
    if block_type == "link_preview":
        url = data.get("url", "")
        return f"[{url}]({url})"
    if block_type == "mention":
        return _block_dict_to_text(data)
    if block_type == "numbered_list_item":
        text = f"{pos+1}. " + _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "paragraph":
        text = _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "pdf":
        image_type = data.get("type")
        url = data.get(image_type, {}).get("url")
        return f"![{url}]({url})"
    if block_type == "quote":
        text = "> " + _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "synced_block":
        # TODO - Handle duplicate synced block
        return _format_children(block_dict)
    if block_type == "table":
        # TODO - Retrieve full table
        return f"[Table](table_id={block_dict.get('id')})"
    if block_type == "table_of_contents":
        pass
    if block_type == "to_do":
        if data.get("checked"):
            prefix = "- [x]"
        else:
            prefix = "- [ ]"
        text = prefix + _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "toggle":
        text = _rich_text_arr_to_text(data.get("rich_text"))
        return text + _format_children(block_dict)
    if block_type == "video":
        image_type = data.get("type")
        url = data.get(image_type, {}).get("url")
        return f"![{url}]({url})"
    return ""


def get_page_blocks(page_id: str, num_blocks: int = 100) -> list[NotionBlock]:
    """
    Retrieves a list of blocks for a page

    Args:
    - page_id (str): Page ID to retrieve
    - num_blocks (int): Maximum number of blocks, defaults to 100

    Returns:
        A list of blocks each represented as a dictionary with the following attributes
        - id (str): Page ID
        - created_at (str): Creation timestamp
        - modified_at (str): Last modified timestamp
        - type (str): Block type e.g. "child_page", "paragraph" etc.
        - data (dict): A dictionary containing block data
        - children (list[dict]): List of children blocks if any
    """
    return _get_block_children(page_id, num_blocks)


def get_page_text(page_id: str, num_blocks: int = 100) -> str:
    """
    Retrieves page content as text

    Args:
    - page_id (str): Page ID to retrieve
    - num_blocks (int): Maximum number of blocks, defaults to 100

    Returns:
        A string representing the page content
    """
    blocks = _get_block_children(page_id, num_blocks)
    return "\n".join(_block_dict_to_text(b, i) for i, b in enumerate(blocks))


def create_page(parent_id: str, title: str, content: str) -> str:
    """
    Create a new page in an existing page (but not in an existing database)

    Args:
    - parent_id (str): Page ID of parent page to append the page to
    - title (str): Page title
    - content (str): Page content, supports Markdown syntax

    Returns:
        If successful, returns "Page created with ID {page_id}"
        Else, returns "Something went wrong"
    """
    data = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "id": "title",
                "type": "title",
                "title": [{"type": "text", "text": {"content": title}}],
            }
        },
        "children": md2notion(content),
    }
    response = requests.post(
        API_URL + "/pages",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_INTEGRATION_SECRET']}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        data=json.dumps(data),
    )
    if response.ok:
        response_json = response.json()
        return f"Page created with ID {response_json.get('id')}"
    else:
        return "Something went wrong"


def insert_paragraph(
    parent_id: str, content: str, after_block_id: str | None = None
) -> str:
    """
    Insert a paragraph block at the bottom of a page, or after another block

    Args:
    - parent_id (str): Page or block ID of parent to append the paragraph to
    - content (str): Paragraph content, supports Markdown syntax
    - after_block_id (Optional[str]): Append paragraph after this block

    Returns:
        If successful, returns "Paragraph inserted with ID {block_id}"
        Else, returns "Something went wrong"
    """
    data = {"children": md2notion(content)}
    if after_block_id:
        data["after"] = after_block_id
    response = requests.patch(
        API_URL + f"/blocks/{parent_id}/children",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_INTEGRATION_SECRET']}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        data=json.dumps(data),
    )
    if response.ok:
        response_json = response.json()
        blocks = response_json.get("results", [])
        if len(blocks):
            return f"Paragraph inserted with ID {blocks[0].get('id')}"
    return "Something went wrong"
