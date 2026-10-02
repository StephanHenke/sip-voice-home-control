"""Refresh the standalone installer's readable, embedded deployment files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['config.example.yaml', 'deploy/lxc/provision-lxc.sh',
         'deploy/lxc/compose.yaml', 'deploy/lxc/compose.web.yaml',
         'deploy/lxc/voice-home-deploy.sh']


def main():
    path = ROOT / 'deploy/lxc/easy-start.py'
    source = path.read_text(encoding='utf-8')
    before, rest = source.split('# BEGIN BUNDLED FILES\n', 1)
    _, after = rest.split('# END BUNDLED FILES\n', 1)
    entries = []
    for name in FILES:
        content = (ROOT / name).read_text(encoding='utf-8')
        if "'''" in content:
            raise ValueError('Embedded file contains reserved triple quote: ' + name)
        entries.append(f"    {name!r}: r'''{content}''',\n")
    bundle = 'BUNDLED_FILES = {\n' + ''.join(entries) + '}\n'
    result = before + '# BEGIN BUNDLED FILES\n' + bundle + '# END BUNDLED FILES\n' + after
    path.write_text(result, encoding='utf-8', newline='\n')
    header = (ROOT / 'scripts/easy-start-header.sh').read_text(encoding='utf-8')
    marker = 'VOICE_HOME_EMBEDDED_PYTHON'
    if marker in result.splitlines():
        raise ValueError('Reserved shell delimiter in installer')
    shell = header + f"\ncat >\"$installer\" <<'{marker}'\n" + result + f'\n{marker}\n'
    shell += 'python3 "$installer" "$@"\n'
    (ROOT / 'deploy/lxc/easy-start.sh').write_text(shell, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
