"""
Generate llms.txt and llms-full.txt from documentation files.

llms.txt: Generated from mkdocs nav structure with descriptions from page frontmatter
llms-full.txt: Full concatenation of all markdown content
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configuration for which sections to include/exclude
INCLUDE_SECTIONS = ["Getting started", "Concepts", "Guides", "Examples"]
EXCLUDE_SECTIONS = ["Reference"]


def read_frontmatter(file_path: Path) -> Dict[str, Any]:
    """Read YAML frontmatter from markdown file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                if isinstance(frontmatter, dict):
                    return frontmatter
    except Exception as e:
        print(f"Warning: Failed to read frontmatter from {file_path}: {e}")
    return {}


def get_page_info(page_path: str, docs_dir: Path, repo_root: Path) -> Optional[Dict[str, str]]:
    """Get title and description for a page from its frontmatter."""
    # page_path is relative to docs_dir
    full_path = docs_dir / page_path

    # For examples/**/index.md, read from README.md at repo root (same logic as hooks.py)
    if page_path.startswith("examples/") and page_path.endswith("index.md"):
        example_dir = Path(page_path).parent
        readme_path = repo_root / example_dir / "README.md"
        if readme_path.exists():
            full_path = readme_path

    if not full_path.exists():
        return None

    frontmatter = read_frontmatter(full_path)

    # Get title from frontmatter or filename
    title = frontmatter.get("title")
    if not title:
        # Use filename as fallback
        title = full_path.stem.replace("-", " ").title()

    # Get description from frontmatter
    description = frontmatter.get("description", "")

    return {"title": title, "description": description}


def parse_mkdocs_nav(mkdocs_config: Dict[str, Any], repo_root: str) -> List[Dict[str, Any]]:
    """Parse mkdocs nav structure and extract relevant sections."""
    nav = mkdocs_config.get("nav", [])
    sections = []

    # Get docs_dir from config
    docs_dir = Path(repo_root) / mkdocs_config.get("docs_dir", "docs")
    repo_root_path = Path(repo_root)

    def extract_pages(content_list):
        """Recursively extract all pages from a section's content, including nested subsections."""
        items = []
        for item in content_list:
            if isinstance(item, str):
                # Plain string path like "examples.md"
                page_info = get_page_info(item, docs_dir, repo_root_path)
                if page_info:
                    items.append(
                        {
                            "type": "page",
                            "title": page_info["title"],
                            "path": item,
                            "description": page_info["description"],
                        }
                    )
            elif isinstance(item, dict):
                for title, path in item.items():
                    if isinstance(path, str):
                        # Page with title
                        page_info = get_page_info(path, docs_dir, repo_root_path)
                        if page_info:
                            items.append(
                                {
                                    "type": "page",
                                    "title": title,  # Use title from nav
                                    "path": path,
                                    "description": page_info["description"],
                                }
                            )
                    elif isinstance(path, list):
                        # Nested subsection - create subsection with its pages
                        subsection_items = extract_pages(path)
                        if subsection_items:
                            items.append(
                                {
                                    "type": "subsection",
                                    "title": title,
                                    "items": subsection_items,
                                }
                            )
        return items

    def process_nav_items(nav_items):
        """Recursively process nav items to find matching sections."""
        for item in nav_items:
            if isinstance(item, dict):
                for section_name, section_content in item.items():
                    # Check if this section should be included
                    if section_name in INCLUDE_SECTIONS and section_name not in EXCLUDE_SECTIONS:
                        # Extract all pages from this section, including nested subsections
                        items = []
                        if isinstance(section_content, list):
                            items = extract_pages(section_content)

                        if items:
                            sections.append(
                                {
                                    "title": section_name,
                                    "items": items,
                                }
                            )

                    # Recursively process nested sections
                    elif isinstance(section_content, list):
                        process_nav_items(section_content)

    process_nav_items(nav)
    return sections


def generate_llms_txt(repo_root: str, mkdocs_config: Dict[str, Any], output_path: str) -> None:
    """Generate llms.txt from mkdocs nav structure."""
    # Get title, description, and base_url from mkdocs config
    title = mkdocs_config.get("site_name", "")
    description = mkdocs_config.get("site_description", "")
    base_url = mkdocs_config.get("site_url", "").rstrip("/")

    lines = []

    # Title and description
    lines.append(f"# {title}\n")
    lines.append(f"> {description}\n")

    # Parse sections from mkdocs nav
    sections = parse_mkdocs_nav(mkdocs_config, repo_root)

    # Generate sections
    def render_items(items, indent_level=0):
        """Render items (pages and subsections) with proper formatting."""
        rendered = []
        for item in items:
            if item["type"] == "page":
                # Use .md paths as-is since hooks.py copies them to site
                url = f"{base_url}/{item['path']}"
                if item["description"]:
                    rendered.append(f"- [{item['title']}]({url}): {item['description']}")
                else:
                    rendered.append(f"- [{item['title']}]({url})")
            elif item["type"] == "subsection":
                # Render subsection header
                rendered.append(f"\n### {item['title']}\n")
                # Render subsection items
                rendered.extend(render_items(item["items"], indent_level + 1))
        return rendered

    for section in sections:
        lines.append(f"## {section['title']}\n")
        lines.extend(render_items(section["items"]))
        lines.append("")

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_llms_full_txt(
    repo_root: str, mkdocs_config: Dict[str, Any], output_path: str
) -> None:
    """Generate llms-full.txt by concatenating all pages from llms.txt sections."""
    content_parts = []

    # Get docs_dir from config
    docs_dir = Path(repo_root) / mkdocs_config.get("docs_dir", "docs")

    # Parse sections from mkdocs nav (same as llms.txt)
    sections = parse_mkdocs_nav(mkdocs_config, repo_root)

    def extract_page_paths(items):
        """Recursively extract all page paths from items (including nested subsections)."""
        paths = []
        for item in items:
            if item["type"] == "page":
                paths.append(item["path"])
            elif item["type"] == "subsection":
                paths.extend(extract_page_paths(item["items"]))
        return paths

    # Concatenate all pages from all sections
    for section in sections:
        for page_path in extract_page_paths(section["items"]):
            full_path = docs_dir / page_path

            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    content_parts.append(f"# {page_path}\n\n{content}\n\n")
                except Exception as e:
                    print(f"Warning: Failed to read {page_path}: {e}")
            else:
                print(f"Warning: File not found: {page_path}")

    # Write to file
    if content_parts:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("".join(content_parts))
    else:
        print("Warning: No content found for llms-full.txt")


def generate_llms_files(repo_root: str, site_dir: str, mkdocs_config: Dict[str, Any]) -> None:
    """Generate both llms.txt and llms-full.txt."""
    llms_txt_path = os.path.join(site_dir, "llms.txt")
    llms_full_txt_path = os.path.join(site_dir, "llms-full.txt")

    print("Generating llms.txt from mkdocs nav...")
    generate_llms_txt(repo_root, mkdocs_config, llms_txt_path)
    print("Generated llms.txt")

    print("Generating llms-full.txt...")
    generate_llms_full_txt(repo_root, mkdocs_config, llms_full_txt_path)
    print("Generated llms-full.txt")
