import unittest,textwrap
from pathlib import Path
class WorkflowPython(unittest.TestCase):
    def test_embedded_python_compiles(self):
        for path in (Path(__file__).resolve().parents[1]/'.github/workflows').glob('*.yml'):
            lines=path.read_text(encoding='utf8').splitlines();block=None
            for line in lines:
                if line.strip()=="python - <<'PY'":block=[]
                elif block is not None:
                    if line.strip()=='PY':
                        with self.subTest(workflow=path.name):compile(textwrap.dedent('\n'.join(block)),str(path),'exec')
                        block=None
                    else:block.append(line)
