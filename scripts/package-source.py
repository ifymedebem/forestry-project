"""Build the downloadable source bundle without credentials or local state."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent.parent
destination = root / 'public/downloads/canopy-source.zip'
destination.parent.mkdir(parents=True, exist_ok=True)
files = ['package.json', 'package-lock.json', 'next.config.ts', 'tsconfig.json', 'next-env.d.ts', 'requirements.txt', 'Dockerfile', 'compose.yaml', '.dockerignore', '.gitignore', '.env.example', 'README.md', 'VERIFICATION.md']
directories = ['app', 'components', 'lib', 'backend', 'tests', 'examples', 'scripts', 'public/images']
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        path = root / name
        if path.exists():
            archive.write(path, 'canopy-evidence/' + name)
    for name in directories:
        for path in sorted((root / name).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.zip'):
                archive.write(path, 'canopy-evidence/' + str(path.relative_to(root)))
print(f'Source bundle: {destination.stat().st_size:,} bytes')
