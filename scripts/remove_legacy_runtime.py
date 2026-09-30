"""Run only after stopping the old controller; never delete the data volume."""
import argparse
from pathlib import Path


def remove_legacy(directory):
    root = Path(directory).resolve(strict=True)
    removed = []
    for name in ('callbacks.sqlite', 'callbacks.sqlite-wal', 'callbacks.sqlite-shm',
                 'callbacks.sqlite-journal', 'health.json', 'health.tmp'):
        path = root / name
        if path.is_symlink():
            raise ValueError('Refusing a symlink in legacy runtime data')
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='/data')
    args = parser.parse_args()
    for name in remove_legacy(args.data_dir):
        print('removed', name)
