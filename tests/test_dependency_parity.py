from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def normalized_requirements(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith(('#', '-r '))
    }


def test_requirements_txt_matches_pyproject_runtime_dependencies():
    pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    canonical = set(pyproject['project']['dependencies'])
    requirements = normalized_requirements(ROOT / 'requirements.txt')
    assert requirements == canonical, (
        'requirements.txt must remain in exact parity with pyproject.toml runtime dependencies. '
        f'Missing from requirements.txt: {sorted(canonical - requirements)}; '
        f'extra in requirements.txt: {sorted(requirements - canonical)}'
    )
