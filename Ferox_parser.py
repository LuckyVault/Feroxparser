import re
import json
import sys
from html import escape
from urllib.parse import urlparse

def parse_size(size_str):
    """
    Parses the size string from the feroxbuster output and converts it into a human-readable format.
    """
    match = re.search(r'(\d+)c', size_str)
    if not match:
        return ''
    bytes_size = int(match.group(1))
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{(bytes_size / 1024):.1f} KB"
    else:
        return f"{(bytes_size / (1024 * 1024)):.1f} MB"

def parse_ferox_line(line, base_url):
    """
    Parses each line of the feroxbuster output to extract relevant information.
    """
    parts = line.strip().split()
    if len(parts) < 6:
        return None
    if parts[0] != '200':
        return None
    full_url = parts[-1]
    if full_url.startswith(base_url):
        path = full_url.replace(base_url, '', 1)
    else:
        # Extract the path component from the URL
        parsed_url = urlparse(full_url)
        path = parsed_url.path
    size = parse_size(parts[4])
    return path, size

def deduplicate_files(files):
    """
    Deduplicate files ignoring case but preserving original case for display.
    """
    deduplicated = {}
    for path, size in files.items():
        lower_path = path.lower()
        if lower_path not in deduplicated or path.isupper():
            deduplicated[lower_path] = (path, size)
    return {original_path: size for lower_path, (original_path, size) in deduplicated.items()}

def categorize_critical_files(files):
    """
    Categorize files into Critical based on predefined criteria.
    """
    critical_extensions = [
        '.sql', '.db', '.sqlite', '.mdb', '.accdb',    # Database Files
        '.pwd', '.key',                                 # Password Files
        '.kdbx', '.psafe3',                             # Password Manager Files
        '.bak', '.backup', '.old'                       # Backup and Archive Files
    ]
    critical_names = ['database', 'db', 'sql', 'password']

    categorized = []

    for path, size in files.items():
        filename = path.split('/')[-1].lower()
        # Check extensions
        if any(filename.endswith(ext) for ext in critical_extensions):
            categorized.append({'path': path, 'size': size})
            continue
        # Check specific names
        if any(name in filename for name in critical_names):
            categorized.append({'path': path, 'size': size})
            continue

    return categorized

def build_tree(files, critical_files):
    """
    Constructs a nested dictionary representing the directory tree from the list of files.
    Critical files are marked for highlighting.
    """
    class TreeNode:
        def __init__(self, name, size=None, is_critical=False):
            self.name = name
            self.size = size
            self.is_critical = is_critical
            self.children = {}

        def to_dict(self):
            result = {"name": self.name}
            if self.size:
                result["size"] = self.size
            if self.is_critical:
                result["is_critical"] = self.is_critical
            if self.children:
                result["children"] = [child.to_dict() for child in sorted(self.children.values(), key=lambda x: x.name.lower())]
            return result

    # Create a set for quick critical file lookup
    critical_set = set(item['path'].lower() for item in critical_files)

    root = TreeNode("")

    files = deduplicate_files(files)

    for path, size in sorted(files.items(), key=lambda x: x[0].lower()):
        current = root
        parts = path.strip('/').split('/')
        for i, part in enumerate(parts):
            lower_part = part.lower()
            if lower_part not in current.children:
                # Determine if the current part is a critical file
                if i == len(parts) - 1:
                    is_critical = path.lower() in critical_set
                else:
                    is_critical = False
                current.children[lower_part] = TreeNode(part, size if i == len(parts) - 1 else None, is_critical)
            current = current.children[lower_part]
    return root.to_dict()

def generate_html(tree_data, critical_files, base_url):
    """
    Generates an interactive HTML report based on the directory tree data and critical files.
    """
    # Escape double braces for JavaScript template literals
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Directory Structure Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            margin-bottom: 20px;
        }}
        .tree-node {{
            margin-left: 20px;
        }}
        .node-content {{
            display: flex;
            align-items: center;
            padding: 4px;
            border-radius: 4px;
        }}
        .node-content:hover {{
            background-color: #f0f0f0;
        }}
        .expander {{
            cursor: pointer;
            width: 20px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-right: 5px;
            font-family: monospace;
        }}
        .checkbox {{
            width: 16px;
            height: 16px;
            margin-right: 8px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid #ccc;
            border-radius: 3px;
        }}
        .checkbox.red-x {{
            color: red;
            font-weight: bold;
        }}
        .checkbox.green-check {{
            color: green;
            font-weight: bold;
        }}
        .icon {{
            margin-right: 5px;
            font-family: monospace;
        }}
        .node-name {{
            flex-grow: 1;
        }}
        .size {{
            color: #666;
            font-size: 0.9em;
            margin-left: 8px;
        }}
        .file-extension {{
            font-weight: bold;
        }}
        .tracked-files {{
            position: fixed;
            top: 20px;
            right: 20px;
            width: 300px;
            max-height: 80vh;
            overflow-y: auto;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            display: none;
            z-index: 1000;
        }}
        .tracked-files.visible {{
            display: block;
        }}
        .tracked-item {{
            padding: 4px 0;
            border-bottom: 1px solid #eee;
        }}
        .instructions {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }}
        .instructions ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        a {{
            color: inherit;
            text-decoration: none;
        }}
        a:hover {{
            color: #0366d6;
        }}
        /* Highlighting Styles */
        .highlight-critical {{
            box-shadow: 0 0 10px 2px red;
        }}
        /* Category Box */
        .category-box {{
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 20px;
            color: white;
            background-color: #e74c3c; /* Red */
        }}
        .category-box h2 {{
            margin-top: 0;
        }}
        .category-list a {{
            display: block;
            color: white;
            text-decoration: underline;
            margin: 2px 0;
        }}
        .category-list a:hover {{
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Directory Structure Report</h1>
        <!-- Critical Files Summary Box -->
        <div class="category-summary">
            {f'''
            <div class="category-box">
                <h2>Critical Files</h2>
                <div class="category-list">
                    {''.join([f'<a href="{escape(base_url + "/" + item["path"])}" target="_blank">{escape(item["path"])}</a>' for item in critical_files])}
                </div>
            </div>
            ''' if critical_files else ''}
        </div>
        <div class="instructions">
            <p>👉 Click directory checkboxes to mark status:</p>
            <ul>
                <li>Once: Red X (marked for deletion/review)</li>
                <li>Twice: Green checkmark (tracked)</li>
                <li>Files marked with green checkmarks appear in the tracked files panel</li>
            </ul>
            <p>📂 Click the arrows to expand/collapse directories</p>
        </div>
        <div id="tree-root"></div>
    </div>
    <div id="tracked-files" class="tracked-files">
        <h2>Tracked Files (<span id="tracked-count">0</span>)</h2>
        <div id="tracked-list"></div>
    </div>

    <script>
        const treeData = {json.dumps(tree_data)};
        const criticalFiles = {json.dumps([item['path'].lower() for item in critical_files])};

        function formatFileName(name) {{
            const parts = name.split('.');
            if (parts.length <= 1) return name;
            return `${{parts.slice(0, -1).join('.')}}<span class="file-extension">.${{parts.pop()}}</span>`;
        }}

        function updateTrackedFiles() {{
            const trackedFiles = [];
            document.querySelectorAll('.checkbox[data-state="2"]').forEach(checkbox => {{
                const nodeContent = checkbox.closest('.node-content');
                const name = nodeContent.querySelector('.node-name').textContent;
                const size = nodeContent.querySelector('.size')?.textContent || '';
                const path = nodeContent.querySelector('a')?.href || '';
                const isDirectory = nodeContent.querySelector('.icon').textContent.includes('📁');
                trackedFiles.push({{ name, size, path, isDirectory }});
            }});

            const trackedFilesPanel = document.getElementById('tracked-files');
            const trackedList = document.getElementById('tracked-list');
            const trackedCount = document.getElementById('tracked-count');

            if (trackedFiles.length > 0) {{
                trackedFilesPanel.classList.add('visible');
                trackedCount.textContent = trackedFiles.length;
                trackedList.innerHTML = trackedFiles.map(file => `
                    <div class="tracked-item">
                        <span>${{file.isDirectory ? '📁' : '📄'}}</span>
                        <a href="${{file.path}}" target="_blank">${{file.name}}</a>
                        ${{file.size ? `<span class="size">${{file.size}}</span>` : ''}}
                    </div>
                `).join('');
            }} else {{
                trackedFilesPanel.classList.remove('visible');
            }}
        }}

        function createTreeNode(node, parentPath = '') {{
            const div = document.createElement('div');
            div.className = 'tree-node';

            const nodeContent = document.createElement('div');
            nodeContent.className = 'node-content';

            // Construct the full path
            const currentPath = parentPath ? `${{parentPath}}/${{node.name}}` : node.name;

            // Apply highlighting if the file is critical
            if (criticalFiles.includes(currentPath.toLowerCase())) {{
                nodeContent.classList.add('highlight-critical');
            }}

            const hasChildren = node.children && node.children.length > 0;
            
            if (hasChildren) {{
                const expander = document.createElement('span');
                expander.className = 'expander';
                expander.textContent = '▼';  // Start expanded
                expander.onclick = () => {{
                    const childContainer = div.querySelector('.children');
                    const isExpanded = expander.textContent === '▼';
                    expander.textContent = isExpanded ? '▶' : '▼';
                    childContainer.style.display = isExpanded ? 'none' : 'block';
                }};
                nodeContent.appendChild(expander);
            }} else {{
                const spacer = document.createElement('span');
                spacer.style.width = '20px';
                spacer.style.display = 'inline-block';
                nodeContent.appendChild(spacer);
            }}

            const checkbox = document.createElement('div');
            checkbox.className = 'checkbox';
            checkbox.dataset.state = '0';
            checkbox.onclick = () => {{
                const currentState = parseInt(checkbox.dataset.state);
                const newState = (currentState + 1) % 3;
                checkbox.dataset.state = newState;
                checkbox.className = 'checkbox ' + 
                    (newState === 1 ? 'red-x' : newState === 2 ? 'green-check' : '');
                checkbox.textContent = newState === 1 ? '❌' : newState === 2 ? '✓' : '';
                updateTrackedFiles();
            }};
            nodeContent.appendChild(checkbox);

            const icon = document.createElement('span');
            icon.className = 'icon';
            icon.textContent = hasChildren ? '📁' : '📄';
            nodeContent.appendChild(icon);

            const nameContainer = document.createElement('a');
            nameContainer.className = 'node-name';
            // Use the correct base URL here
            const baseUrl = "{escape(base_url)}";  // Updated base URL
            nameContainer.href = `${{baseUrl}}/${{currentPath}}`;
            nameContainer.target = '_blank';
            nameContainer.innerHTML = hasChildren ? escapeHtml(node.name) : formatFileName(escapeHtml(node.name));
            nodeContent.appendChild(nameContainer);

            if (node.size) {{
                const size = document.createElement('span');
                size.className = 'size';
                size.textContent = `[${{node.size}}]`;
                nodeContent.appendChild(size);
            }}

            div.appendChild(nodeContent);

            if (hasChildren) {{
                const childContainer = document.createElement('div');
                childContainer.className = 'children';
                childContainer.style.display = 'block';  // Start expanded
                node.children.forEach(child => {{
                    childContainer.appendChild(
                        createTreeNode(child, currentPath)
                    );
                }});
                div.appendChild(childContainer);
            }}

            return div;
        }}

        function escapeHtml(text) {{
            const map = {{
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            }};
            return text.replace(/[&<>"']/g, function(m) {{ return map[m]; }});
        }}

        // Initialize the tree
        document.getElementById('tree-root').appendChild(createTreeNode(treeData));
    </script>
</body>
</html>"""

def main():
    """
    Main function to parse feroxbuster results, categorize critical files, build the directory tree,
    and generate the HTML report.
    """
    if len(sys.argv) != 2:
        print("Usage: python3 Ferox_parser.py ferox_scan_results.txt")
        sys.exit(1)

    input_file = sys.argv[1]
    base_url = 'http://192.168.244.141:81'  # Update this to match your feroxbuster scan URL

    print("Starting to parse feroxbuster results...")
    try:
        with open(input_file, 'r') as f:
            print(f"Reading {input_file}...")
            lines = f.readlines()

        files = {}
        duplicates = 0
        for line in lines:
            result = parse_ferox_line(line, base_url + '/')
            if result:
                path, size = result
                if path.lower() in {p.lower() for p in files.keys()}:
                    duplicates += 1
                files[path] = size

        print(f"Found {len(files)} files with 200 status code")
        print(f"Removed {duplicates} duplicate entries")

        print("Categorizing critical files...")
        critical_files = categorize_critical_files(files)

        print("Building directory tree structure...")
        tree = build_tree(files, critical_files)

        print("Generating HTML report...")
        html_output = generate_html(tree, critical_files, base_url)

        output_file = 'ferox_report.html'
        with open(output_file, 'w') as f:
            f.write(html_output)

        print(f"\nSuccess! Report generated: {output_file}")
        print(f"Total unique files processed: {len(files)}")
        print(f"Total critical files identified: {len(critical_files)}")
        print("\nOpen the HTML file in your browser to view the report.")

    except FileNotFoundError:
        print(f"Error: Could not find {input_file}")
        print(f"Please make sure to save your feroxbuster output to {input_file} in the same directory as this script.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
