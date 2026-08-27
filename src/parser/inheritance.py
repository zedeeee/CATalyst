"""
Inheritance Analyzer Module for CATalyst.
Parses jsTree.js from CATIA CHM documentation to build the complete class hierarchy tree.
"""
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class InheritanceTree:
    def __init__(self, js_tree_path: Path):
        self.js_tree_path = js_tree_path
        # Maps child_id -> parent_id
        self.father_links: Dict[str, str] = {}
        self._build_tree()

    def _build_tree(self):
        """Parses jsTree.js to extract fatherLink relationships."""
        if not self.js_tree_path.exists():
            logger.error(f"Cannot find jsTree.js at {self.js_tree_path}")
            return
            
        with open(self.js_tree_path, 'r', encoding='iso-8859-1') as f:
            content = f.read()
            
        # Pattern: fatherLink["interface_Pad_13505"]="interface_Prism_14313";
        pattern = re.compile(r'fatherLink\["([^"]+)"\]\s*=\s*"([^"]+)";')
        
        matches = pattern.findall(content)
        for child_id, parent_id in matches:
            self.father_links[child_id] = parent_id
            
        logger.info(f"Loaded {len(self.father_links)} inheritance relationships.")

    def get_parent(self, class_id: str) -> Optional[str]:
        """Returns the parent ID of a given class ID."""
        return self.father_links.get(class_id)

    def get_ancestors(self, class_id: str) -> List[str]:
        """Returns a list of all ancestor IDs, ordered from direct parent to root."""
        ancestors = []
        current = class_id
        while True:
            parent = self.get_parent(current)
            if not parent:
                break
            # To prevent infinite loops in case of bad data
            if parent in ancestors:
                logger.warning(f"Circular inheritance detected for {parent}")
                break
            ancestors.append(parent)
            current = parent
        return ancestors

if __name__ == "__main__":
    import argparse
    import json
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Test Inheritance Tree")
    parser.add_argument("--jstree", type=str, default="data/raw/generated/interfaces/_index/jsTree.js")
    parser.add_argument("class_id", type=str, help="e.g., interface_Pad_13505")
    
    args = parser.parse_args()
    
    tree = InheritanceTree(Path(args.jstree))
    ancestors = tree.get_ancestors(args.class_id)
    print(json.dumps({
        "class_id": args.class_id,
        "ancestors": ancestors
    }, indent=2))
