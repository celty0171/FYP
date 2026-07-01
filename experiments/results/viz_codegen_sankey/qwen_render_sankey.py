import json
import sys
import argparse
import os
import html
from typing import Dict, List, Any
import urllib.parse
import re

def render(mapping: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    source_col = mapping.get("source")
    target_col = mapping.get("target")
    width_col = mapping.get("width")
    title = mapping.get("title", f"{source_col} → {target_col} Sankey diagram")

    # Aggregate flows by source-target pair
    flows = {}
    for row in rows:
        source = row.get(source_col)
        target = row.get(target_col)
        width = row.get(width_col, 0)
        if source is None or target is None or width is None:
            continue
        key = (source, target)
        flows[key] = flows.get(key, 0) + width

    # Prepare nodes and links for Google Charts
    nodes = set()
    links = []
    for (source, target), width in flows.items():
        nodes.add(source)
        nodes.add(target)
        links.append({"source": source, "target": target, "value": width})

    # Sort nodes for deterministic rendering
    sorted_nodes = sorted(nodes)
    node_to_index = {node: idx for idx, node in enumerate(sorted_nodes)}

    # Convert to Google Charts format
    google_nodes = [{"name": node} for node in sorted_nodes]
    google_links = [
        {
            "source": node_to_index[source],
            "target": node_to_index[target],
            "value": width
        }
        for (source, target), width in flows.items()
    ]

    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{html.escape(title)}</title>
        <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
            }}
            #sankey {{
                width: 100%;
                height: 600px;
                border: 1px solid #ccc;
            }}
        </style>
    </head>
    <body>
        <h1>{html.escape(title)}</h1>
        <div id="sankey"></div>
        <script type="text/javascript">
            google.charts.load('current', {{'packages':['sankey']}});
            google.charts.setOnLoadCallback(drawChart);

            function drawChart() {{
                var data = new google.visualization.DataTable();
                data.addColumn('string', 'From');
                data.addColumn('string', 'To');
                data.addColumn('number', 'Value');

                {"".join([f"data.addRows([[\"{html.escape(source)}\", \"{html.escape(target)}\", {width}]]);" for (source, target), width in flows.items()])}

                var options = {{
                    width: '100%',
                    height: 600,
                    node: {{
                        color: '#666',
                        label: 'name'
                    }},
                    link: {{
                        color: '#333'
                    }},
                    sankey: {{
                        iterations: 0,
                        node: {{
                            label: 'name'
                        }},
                        link: {{
                            color: 'source',
                            colorMode: 'gradient',
                            gradient: {{
                                colors: [
                                    '#3366cc',
                                    '#5cd6d6',
                                    '#ffffff',
                                    '#f9bc60',
                                    '#f97c3d',
                                    '#f94e1b'
                                ]
                            }}
                        }}
                    }}
                }};

                var chart = new google.visualization.Sankey(document.getElementById('sankey'));
                chart.draw(data, options);
            }}
        </script>
    </body>
    </html>
    """

    return html_content

def main():
    parser = argparse.ArgumentParser(description="Render a Sankey diagram from mapping and data files.")
    parser.add_argument("--mapping", required=True, help="Path to the mapping JSON file.")
    parser.add_argument("--data", required=True, help="Path to the data JSON file.")
    parser.add_argument("--out", required=True, help="Path to output the HTML file.")
    args = parser.parse_args()

    # Load mapping
    with open(args.mapping, "r") as f:
        mapping = json.load(f)

    # Load data
    with open(args.data, "r") as f:
        rows = json.load(f)

    # Render HTML
    html_content = render(mapping, rows)

    # Write to output file
    with open(args.out, "w") as f:
        f.write(html_content)

    print(f"Rendered Sankey diagram saved to {args.out}")

if __name__ == "__main__":
    main()
