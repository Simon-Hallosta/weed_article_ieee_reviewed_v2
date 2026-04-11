#!/usr/bin/env python3
"""Build a latexdiff PDF for the IEEE Access manuscript.

The script is intentionally parameterized so a Codex skill can choose both the
baseline/original TeX file and the revised TeX file without rewriting commands.
It prefers native tools on PATH and falls back to MiKTeX tools through cmd.exe
when run from WSL.
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_OLD = "../IEEE_Access_before_review/access_revised_v2.tex"
DEFAULT_NEW = "access_revised_v2.tex"

AUX_SUFFIXES = (
    ".aux",
    ".bbl",
    ".bcf",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".run.xml",
    ".synctex.gz",
    ".toc",
)

LOG_PROBLEM_PATTERNS = (
    re.compile(r"! LaTeX Error"),
    re.compile(r"Emergency stop"),
    re.compile(r"Fatal error"),
    re.compile(r"Fatal Error"),
    re.compile(r"Citation `[^']+' .* undefined"),
    re.compile(r"LaTeX Warning: There were undefined references"),
)


@dataclass(frozen=True)
class Tool:
    name: str
    executable: str
    mode: str  # "native" or "cmd"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a latexdiff TeX file and optionally compile it to PDF."
        )
    )
    parser.add_argument(
        "--old",
        "--original",
        default=DEFAULT_OLD,
        help=f"Original/baseline TeX file. Default: {DEFAULT_OLD}",
    )
    parser.add_argument(
        "--new",
        "--revised",
        default=DEFAULT_NEW,
        help=f"Revised TeX file. Default: {DEFAULT_NEW}",
    )
    parser.add_argument(
        "--output-name",
        "--name",
        help=(
            "Output stem without extension. Default: "
            "<new-stem>_diff_<baseline-dir>."
        ),
    )
    parser.add_argument(
        "--tex-only",
        action="store_true",
        help="Only generate the diff .tex file; do not run latexmk.",
    )
    parser.add_argument(
        "--clean-aux",
        action="store_true",
        help="Remove auxiliary LaTeX files for the generated diff after build.",
    )
    parser.add_argument(
        "--strict-log",
        action="store_true",
        help="Exit non-zero if the final LaTeX log has unresolved references.",
    )
    parser.add_argument(
        "--skip-log-check",
        action="store_true",
        help="Do not scan the final LaTeX log after a PDF build.",
    )
    parser.add_argument(
        "--latexdiff-bin",
        default="latexdiff",
        help="latexdiff executable name or path. Default: latexdiff",
    )
    parser.add_argument(
        "--latexmk-bin",
        default="latexmk",
        help="latexmk executable name or path. Default: latexmk",
    )
    parser.add_argument(
        "--latexdiff-option",
        action="append",
        default=[],
        help="Extra option passed to latexdiff. Can be repeated.",
    )
    parser.add_argument(
        "--latexmk-option",
        action="append",
        default=[],
        help="Extra option passed to latexmk. Can be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned actions without writing or running tools.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full commands before running them.",
    )
    return parser.parse_args(argv)


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def is_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    release = platform.release().lower()
    if "microsoft" in release or "wsl" in release:
        return True
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "microsoft" in proc_version or "wsl" in proc_version


def quote_cmd_arg(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[ \t&()^=;!,`~\[\]{}"]', value):
        return '"' + value.replace('"', r"\"") + '"'
    return value


def wsl_to_windows(path: Path) -> str:
    completed = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def path_for_tool(path: Path, tool: Tool) -> str:
    resolved = path.resolve()
    if tool.mode == "cmd" and is_wsl():
        return wsl_to_windows(resolved)
    return str(resolved)


def tool_command(tool: Tool, args: Iterable[str | Path], _cwd: Path) -> list[str]:
    if tool.mode == "native":
        return [tool.executable, *[str(arg) for arg in args]]

    converted_args: list[str] = []
    for arg in args:
        if isinstance(arg, Path):
            converted_args.append(path_for_tool(arg, tool))
        else:
            converted_args.append(arg)
    # Keep cmd.exe invocation as separate argv items. A single /c command string
    # is fragile with spaces in OneDrive paths and nested quotes.
    return ["cmd.exe", "/c", tool.executable, *converted_args]


def run(
    command: list[str],
    cwd: Path,
    *,
    capture_stdout: bool = False,
    verbose: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    if verbose:
        print("+ " + " ".join(quote_cmd_arg(part) for part in command))
    return subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE,
    )


def is_explicit_path(value: str) -> bool:
    return any(separator in value for separator in ("/", "\\")) or value.endswith(".exe")


def find_tool(name_or_path: str, label: str) -> Tool:
    if is_explicit_path(name_or_path):
        path = Path(name_or_path)
        if path.exists():
            return Tool(label, str(path), "native")

    native = shutil.which(name_or_path)
    if native:
        return Tool(label, native, "native")

    if shutil.which("cmd.exe"):
        where = subprocess.run(
            ["cmd.exe", "/c", "where", name_or_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if where.returncode == 0:
            return Tool(label, name_or_path, "cmd")

    raise RuntimeError(
        f"Could not find {label!r}. Install it, add it to PATH, or pass --{label}-bin."
    )


def resolve_input(path_text: str, base: Path) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def default_output_name(old_file: Path, new_file: Path) -> str:
    baseline_slug = slugify(old_file.parent.name)
    return f"{new_file.stem}_diff_{baseline_slug}"


def slugify(value: str) -> str:
    value = value.replace("IEEE_Access_", "")
    value = value.replace("Access_", "")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "baseline"


def validate_inputs(old_file: Path, new_file: Path) -> None:
    missing = [path for path in (old_file, new_file) if not path.is_file()]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(f"Required TeX file(s) not found:\n{formatted}")
    if old_file == new_file:
        raise ValueError("--old and --new point to the same file.")


def generate_diff_tex(
    *,
    old_file: Path,
    new_file: Path,
    output_tex: Path,
    latexdiff: Tool,
    extra_options: Sequence[str],
    cwd: Path,
    dry_run: bool,
    verbose: bool,
) -> None:
    command = tool_command(
        latexdiff,
        [*extra_options, old_file, new_file],
        cwd,
    )
    if dry_run:
        print(f"Would generate: {output_tex}")
        print("+ " + " ".join(quote_cmd_arg(part) for part in command))
        return

    completed = run(command, cwd, capture_stdout=True, verbose=verbose)
    if completed.returncode != 0:
        raise RuntimeError(
            "latexdiff failed:\n"
            + completed.stderr.decode("utf-8", errors="replace")
        )
    if not completed.stdout:
        raise RuntimeError("latexdiff produced no output.")

    output_tex.write_bytes(completed.stdout)


def build_pdf(
    *,
    output_tex: Path,
    latexmk: Tool,
    extra_options: Sequence[str],
    cwd: Path,
    dry_run: bool,
    verbose: bool,
) -> Path:
    command = tool_command(
        latexmk,
        ["-pdf", "-g", *extra_options, output_tex.name],
        cwd,
    )
    output_pdf = output_tex.with_suffix(".pdf")
    if dry_run:
        print(f"Would build: {output_pdf}")
        print("+ " + " ".join(quote_cmd_arg(part) for part in command))
        return output_pdf

    completed = run(command, cwd, verbose=verbose)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"latexmk failed:\n{stderr}")
    if not output_pdf.is_file():
        raise RuntimeError(f"latexmk finished but did not create {output_pdf}.")
    return output_pdf


def scan_log(log_file: Path) -> list[str]:
    if not log_file.is_file():
        return [f"Final log file was not found: {log_file}"]

    problems: list[str] = []
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if any(pattern.search(line) for pattern in LOG_PROBLEM_PATTERNS):
            problems.append(line)
    return problems


def clean_aux_files(output_tex: Path) -> list[Path]:
    removed: list[Path] = []
    for suffix in AUX_SUFFIXES:
        candidate = output_tex.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    return removed


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    project_dir = Path.cwd().resolve()
    old_file = resolve_input(args.old, project_dir)
    new_file = resolve_input(args.new, project_dir)
    validate_inputs(old_file, new_file)

    output_name = args.output_name or default_output_name(old_file, new_file)
    output_tex = (new_file.parent / f"{slugify(output_name)}.tex").resolve()

    if output_tex.parent != new_file.parent.resolve():
        raise ValueError("The diff output must be written next to the revised TeX file.")

    latexdiff = find_tool(args.latexdiff_bin, "latexdiff")
    latexmk = None if args.tex_only else find_tool(args.latexmk_bin, "latexmk")

    print(f"Original: {old_file}")
    print(f"Revised:  {new_file}")
    print(f"Diff TeX: {output_tex}")
    if latexmk is not None:
        print(f"Diff PDF: {output_tex.with_suffix('.pdf')}")
    print(f"latexdiff: {latexdiff.executable} ({latexdiff.mode})")
    if latexmk is not None:
        print(f"latexmk:   {latexmk.executable} ({latexmk.mode})")
    sys.stdout.flush()

    generate_diff_tex(
        old_file=old_file,
        new_file=new_file,
        output_tex=output_tex,
        latexdiff=latexdiff,
        extra_options=args.latexdiff_option,
        cwd=project_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    output_pdf: Path | None = None
    if not args.tex_only and latexmk is not None:
        output_pdf = build_pdf(
            output_tex=output_tex,
            latexmk=latexmk,
            extra_options=args.latexmk_option,
            cwd=project_dir,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    if not args.tex_only and not args.dry_run and not args.skip_log_check:
        problems = scan_log(output_tex.with_suffix(".log"))
        if problems:
            eprint("LaTeX log warnings that may need review:")
            for problem in problems[:20]:
                eprint(f"  {problem}")
            if len(problems) > 20:
                eprint(f"  ... {len(problems) - 20} more")
            if args.strict_log:
                return 1

    if args.clean_aux and not args.dry_run:
        removed = clean_aux_files(output_tex)
        if removed:
            print("Removed auxiliary files:")
            for path in removed:
                print(f"  {path}")

    print("Done.")
    if output_pdf is not None and not args.dry_run:
        print(f"Built PDF: {output_pdf}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        eprint(f"ERROR: {exc}")
        raise SystemExit(1)
