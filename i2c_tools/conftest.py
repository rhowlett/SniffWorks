"""
conftest.py — one pytest runner for every i2c_tools test suite (R9).  [v0.1]

The tests are scripts: each is run as `python <file>` and judged by its exit
code, exactly as before, so nothing in the scripts changes and they still run
on their own. pytest only collects and reports them:

    cd i2c_tools && python -m pytest          # everything
    python -m pytest -k bq25731               # one suite

Collected items (see pytest.ini for the folders):
  * tests/test_*.py, tests/smoke_test.py, loopback_dut/tests/test_*.py:
    one item per script, run in a subprocess.
  * */tests/host/Makefile: one item per C host suite, run as `make -C <dir> test`.

Exit codes: 0 = pass; 77 = loud skip (rig artefacts absent; reported as a
pytest SKIP, never a pass, master plan §5.1); anything else = fail. Scripts
run in subprocesses, so no sniffer code is imported here and the loopback
DUT's isolation rule holds.

Every item gets fresh temporary ION_TOOL_SETTINGS and ION_TOOL_DEVICE_NAMES
files, so no test can write the user's real settings or device names.

EXPECTED_FAIL lists suites that fail for a recorded reason. Like the loopback
ledger (D-05) it is strict: a listed suite that passes is reported as a
failure, so the entry is removed as soon as the cause is fixed.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_TIMEOUT_S = 300
SKIP_EXIT = 77

# suite file name -> reason it is expected to fail today
EXPECTED_FAIL = {
    "test_neware_doc_conformance.py":
        "i2c_decoders/neware_decoder.json is not committed (owner to add)",
}


def pytest_collect_file(file_path: Path, parent):
    """Collect script suites and C host-test Makefiles as runner items.

    Args:
        file_path: Candidate file found by pytest's directory walk.
        parent: The collector of the folder that holds the file.

    Returns:
        A ScriptFile or MakeSuite collector, or None to ignore the file.
    """
    name = file_path.name
    if file_path.suffix == ".py" and (
            (name.startswith("test_") and file_path.parent.name == "tests")
            or name == "smoke_test.py"):
        return ScriptFile.from_parent(parent, path=file_path)
    if name == "Makefile" and file_path.parent.name == "host" \
            and file_path.parent.parent.name == "tests":
        return MakeSuite.from_parent(parent, path=file_path)
    return None


def pytest_pycollect_makemodule(module_path: Path, parent):
    """Stop pytest importing the scripts as modules.

    Their helper functions are named test_* and take arguments, so pytest's
    own collection would report them as broken fixtures. pytest_collect_file
    above already collects each script once.

    Args:
        module_path: The .py file pytest would import.
        parent: Its folder collector.

    Returns:
        An empty collector, so the file yields no Python-level items.
    """
    return _Nothing.from_parent(parent, path=module_path)


class _Nothing(pytest.File):
    """Collector that yields no items (see pytest_pycollect_makemodule)."""

    def collect(self):
        """Yield nothing.

        Returns:
            An empty list.
        """
        return []


class ScriptFile(pytest.File):
    """A script-style suite: one item that runs the file with Python."""

    def collect(self):
        """Yield the single item that runs this script.

        Yields:
            One RunItem named "script".
        """
        yield RunItem.from_parent(
            self, name="script", argv=[sys.executable, str(self.path)],
            cwd=self.path.parent.parent, suite=self.path.name)


class MakeSuite(pytest.File):
    """A C host-test folder: one item that runs `make test` in it."""

    def collect(self):
        """Yield the single item that builds and runs the C tests.

        Yields:
            One RunItem named "make_test".
        """
        yield RunItem.from_parent(
            self, name="make_test", argv=["make", "-C", str(self.path.parent), "test"],
            cwd=self.path.parent, suite=str(self.path.parent.relative_to(self.config.rootpath)))


class SuiteFailed(Exception):
    """A suite exited non-zero; carries its exit code and output tail."""


class RunItem(pytest.Item):
    """Runs one suite in a subprocess and judges it by exit code."""

    def __init__(self, *, argv, cwd, suite, **kwargs):
        """Store what to run.

        Args:
            argv: Command line to execute.
            cwd: Working folder for the command.
            suite: Name used for EXPECTED_FAIL lookup and in reports.
            **kwargs: Passed through to pytest.Item.
        """
        super().__init__(**kwargs)
        self.argv, self.cwd, self.suite = argv, cwd, suite
        reason = EXPECTED_FAIL.get(Path(suite).name)
        if reason:
            self.add_marker(pytest.mark.xfail(reason=reason, strict=True,
                                              raises=SuiteFailed))

    def runtest(self):
        """Run the suite with isolated per-user files and check its exit code.

        Raises:
            SuiteFailed: The suite exited with a code other than 0 or 77.
            pytest.skip.Exception: The suite exited 77 (loud skip).
        """
        with tempfile.TemporaryDirectory(prefix="i2c_tools_test_") as tmp:
            env = dict(os.environ,
                       QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                       ION_TOOL_SETTINGS=str(Path(tmp) / "settings.ini"),
                       ION_TOOL_DEVICE_NAMES=str(Path(tmp) / "device_names.json"))
            proc = subprocess.run(self.argv, cwd=self.cwd, env=env,
                                  capture_output=True, text=True,
                                  timeout=SCRIPT_TIMEOUT_S)
        out = (proc.stdout + proc.stderr).rstrip()
        if proc.returncode == 0:
            return
        if proc.returncode == SKIP_EXIT:
            pytest.skip(f"{self.suite}: exit 77, rig artefacts absent (loud skip)")
        raise SuiteFailed(proc.returncode, "\n".join(out.splitlines()[-40:]))

    def repr_failure(self, excinfo):
        """Show the exit code and the last lines of the suite's output.

        Args:
            excinfo: The captured exception.

        Returns:
            The failure text pytest prints.
        """
        if isinstance(excinfo.value, SuiteFailed):
            code, tail = excinfo.value.args
            return f"{self.suite} exited {code}; last output:\n{tail}"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        """Name the suite in pytest's report lines.

        Returns:
            (path, line, description) for pytest.
        """
        return self.path, None, f"{self.suite} ({' '.join(Path(a).name for a in self.argv[1:2])})"
