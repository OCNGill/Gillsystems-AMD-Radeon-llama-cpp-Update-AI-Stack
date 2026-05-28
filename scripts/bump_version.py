import os
import sys
import re
import json
from datetime import datetime
from pathlib import Path

# Authoritative versioning script for Gillsystems AI Stack Updater

TARGET_FILES = {
    'CHANGELOG.md': 'changelog',
    'README.md': 'readme',
    'UserGuide.md': 'userguide',
    'conductor/index.md': 'conductor_index',
    'conductor/setup_state.json': 'setup_state'
}

def main():
    if len(sys.argv) < 2:
        print("Usage: python bump_version.py <new_version> [optional: 'Commit Message / Phase']")
        print("Example: python bump_version.py 2.2.0 'IT Models Integrated'")
        sys.exit(1)

    new_version = sys.argv[1].replace('v', '')  # ensure no 'v' prefix
    phase_message = sys.argv[2] if len(sys.argv) > 2 else "Routine Update"
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    root_dir = Path(__file__).resolve().parent.parent

    print(f"[Gillsystems] Bumping version to {new_version}...")

    # 1. Update README.md
    readme_path = root_dir / 'README.md'
    if readme_path.exists():
        text = readme_path.read_text(encoding='utf-8')
        # Replace versions in badges
        text = re.sub(r'Release-v\d+\.\d+\.\d+', f'Release-v{new_version}', text)
        text = re.sub(r'\*\*v\d+\.\d+ milestone:\*\*', f'**v{new_version} milestone:**', text)
        readme_path.write_text(text, encoding='utf-8')
        print(" -> Updated README.md")

    # 2. Update UserGuide.md
    guide_path = root_dir / 'UserGuide.md'
    if guide_path.exists():
        text = guide_path.read_text(encoding='utf-8')
        text = re.sub(r'Updater Agent v\d+\.\d+', f'Updater Agent v{new_version}', text)
        text = re.sub(r'> \*\*v\d+\.\d+ — ', f'> **v{new_version} — ', text)
        guide_path.write_text(text, encoding='utf-8')
        print(" -> Updated UserGuide.md")

    # 3. Update Conductor Index
    conductor_idx = root_dir / 'conductor' / 'index.md'
    if conductor_idx.exists():
        text = conductor_idx.read_text(encoding='utf-8')
        text = re.sub(r'\*\*Phase:\*\* Deploy — v\d+\.\d+\.\d+ Released \([^)]+\)', f'**Phase:** Deploy — v{new_version} Released ({phase_message})', text)
        text = re.sub(r'\*\*Last Updated:\*\* \d{4}-\d{2}-\d{2}', f'**Last Updated:** {date_str}', text)
        conductor_idx.write_text(text, encoding='utf-8')
        print(" -> Updated conductor/index.md")

    # 4. Update Setup State
    setup_state = root_dir / 'conductor' / 'setup_state.json'
    if setup_state.exists():
        with open(setup_state, 'r', encoding='utf-8') as f:
            state = json.load(f)
        state['last_successful_step'] = f'v{new_version.replace(".", "_")}_{phase_message.replace(" ", "_").lower()}'
        state['timestamp'] = datetime.now().isoformat()
        with open(setup_state, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        print(" -> Updated conductor/setup_state.json")

    # 5. Prep CHANGELOG.md (adds top-level blueprint)
    changelog_path = root_dir / 'CHANGELOG.md'
    if changelog_path.exists():
        text = changelog_path.read_text(encoding='utf-8')
        if f"## [{new_version}]" not in text:
            new_entry = f"## [{new_version}] — {date_str} — {phase_message}\n\n### Changed\n- \n\n"
            text = re.sub(r'(?m)^(## \[\d+\.\d+\.\d+\])', f'{new_entry}\\1', text, count=1)
            changelog_path.write_text(text, encoding='utf-8')
            print(" -> Scaffolded new version in CHANGELOG.md")
        else:
            print(" -> CHANGELOG.md already has this version.")
            
    print("[Gillsystems] Version bump complete. Please verify the changelog entries manually.")

if __name__ == '__main__':
    main()
