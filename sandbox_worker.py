"""Trusted recorder, mounted inside the disposable lesson sandbox."""
import contextlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import resource
import time
import traceback


class BoundedOutput(io.StringIO):
    def write(self, text):
        if self.tell() + len(text) > 16384:
            raise RuntimeError("lesson_output_limit_16k")
        return super().write(text)


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    notebook = json.loads(Path("/course/lesson.ipynb").read_text(encoding="utf-8"))
    namespace, steps = {"__name__": "__lesson__"}, []
    packages = {}
    for name in ("numpy", "pandas"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        started = time.perf_counter()
        stdout, stderr = BoundedOutput(), BoundedOutput()
        step = {"id": cell["id"], "outcome": "ok"}
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                source = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
                exec(compile(source, cell["id"], "exec"), namespace)
            except Exception as error:
                step.update(outcome="error", error_type=type(error).__name__, error_message=str(error)[:4096])
                try:
                    traceback.print_exc()
                except RuntimeError:
                    pass
        step.update(stdout=stdout.getvalue(), stderr=stderr.getvalue(), elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
        steps.append(step)
    print(json.dumps({"schema_version": 1, "complete": True, "steps": steps,
                      "python": platform.python_version(), "packages": packages}, ensure_ascii=False))


if __name__ == "__main__":
    main()
