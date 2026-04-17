#!/usr/bin/env python3
"""Build a latexdiff PDF for the IEEE Access manuscript.

The script is intentionally parameterized so a Codex skill can choose both the
baseline/original TeX file and the revised TeX file without rewriting commands.
It prefers native tools on PATH and falls back to MiKTeX tools through cmd.exe
when run from WSL.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


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

ANNOTATED_SUFFIX = "_annotated_reviewermap"

ANNOTATION_PREAMBLE = r"""
% Reviewer-comment annotations added after latexdiff generation
\RequirePackage{xcolor}
\RequirePackage{marginnote}
\addtolength{\paperwidth}{10cm}
\setlength{\pdfpagewidth}{\paperwidth}
\addtolength{\oddsidemargin}{5cm}
\addtolength{\evensidemargin}{5cm}
\definecolor{reviewcommentline}{rgb}{0.07,0.24,0.53}
\definecolor{reviewcommentfill}{rgb}{0.94,0.97,1.00}
\definecolor{reviewcommenttext}{rgb}{0.04,0.15,0.34}
\setlength{\marginparwidth}{4.6cm}
\setlength{\marginparsep}{6pt}
\newcommand{\ReviewTodoFormat}[3]{%
  \raggedright
  \sffamily
  \textbf{\textcolor{reviewcommenttext}{#1}}\\[-1pt]
  \textbf{\textcolor{reviewcommenttext}{#2}}\\[2pt]
  \textcolor{reviewcommenttext}{#3}%
}
\newcommand{\ReviewBubble}[3]{%
  \begingroup
  \setlength{\fboxsep}{6pt}%
  \fcolorbox{reviewcommentline}{reviewcommentfill}{%
    \parbox{4.3cm}{\ReviewTodoFormat{#1}{#2}{#3}}%
  }%
  \endgroup
}
\newcommand{\ReviewMarginComment}[3]{%
  \marginnote{\ReviewBubble{#1}{#2}{#3}}%
}
\newcommand{\ReviewInlineComment}[3]{%
  \par\smallskip\noindent\ReviewBubble{#1}{#2}{#3}\par\smallskip
}
"""

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
    parser.add_argument(
        "--annotated-review-comments",
        action="store_true",
        help="Inject reviewer-comment annotations into the generated diff TeX/PDF.",
    )
    parser.add_argument(
        "--review-map",
        help=(
            "JSON file describing reviewer-comment annotations to inject into the "
            "generated diff TeX."
        ),
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


def quote_cmd_exe_arg(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[ \t&()^=;!,`~\[\]{}"]', value):
        return '"' + value.replace('"', '""') + '"'
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
    command_str = " ".join(
        quote_cmd_exe_arg(part) for part in [tool.executable, *converted_args]
    )
    return ["cmd.exe", "/c", command_str]


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
            if path.suffix.lower() == ".exe" and is_wsl():
                return Tool(label, wsl_to_windows(path), "cmd")
            return Tool(label, str(path), "native")

    native = shutil.which(name_or_path)
    if native:
        return Tool(label, native, "native")

    try:
        where = subprocess.run(
            ["cmd.exe", "/c", "where", name_or_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if where.returncode == 0:
            return Tool(label, name_or_path, "cmd")
    except OSError:
        pass

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


def default_annotated_output_name(old_file: Path, new_file: Path) -> str:
    return default_output_name(old_file, new_file) + ANNOTATED_SUFFIX


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


def validate_review_map(review_map: Path) -> None:
    if not review_map.is_file():
        raise FileNotFoundError(f"Review map not found: {review_map}")


def escape_latex_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = "".join(replacements.get(char, char) for char in text)
    return escaped.replace("\n", r"\\ ")


def comment_macro(entry: dict[str, Any]) -> str:
    placement = entry.get("placement", "margin")
    review_id = entry.get("id", "")
    title = entry.get("title") or entry.get("label") or ""
    body = entry.get("body") or ""
    escaped_id = escape_latex_text(review_id)
    escaped_title = escape_latex_text(title)
    escaped_body = escape_latex_text(body)
    if placement == "inline":
        return rf"\ReviewInlineComment{{{escaped_id}}}{{{escaped_title}}}{{{escaped_body}}}"
    if placement == "margin":
        return rf"\ReviewMarginComment{{{escaped_id}}}{{{escaped_title}}}{{{escaped_body}}}"
    raise ValueError(f"Unsupported annotation placement: {placement}")


def insert_annotation_preamble(diff_tex: str) -> str:
    marker = r"\begin{document}"
    if ANNOTATION_PREAMBLE.strip() in diff_tex:
        return diff_tex
    if marker not in diff_tex:
        raise RuntimeError("Could not find \\begin{document} while injecting annotation preamble.")
    return diff_tex.replace(marker, ANNOTATION_PREAMBLE + "\n" + marker, 1)


def append_review_appendix(diff_tex: str, payload: dict[str, Any]) -> str:
    appendix_entries = payload.get("appendix_comments", [])
    if not isinstance(appendix_entries, list) or not appendix_entries:
        return diff_tex

    blocks: list[str] = [
        r"\clearpage",
        r"\section*{Review Comment Mapping Notes}",
        (
            r"This review-only appendix summarizes comments that are addressed "
            r"through distributed or global manuscript revisions and therefore "
            r"are not always captured by a single local diff bubble."
        ),
        r"\begin{itemize}",
    ]

    for entry in appendix_entries:
        if not isinstance(entry, dict):
            raise ValueError("Each appendix comment entry must be an object.")
        review_id = entry.get("id", "")
        title = entry.get("title", "")
        body = entry.get("body", "")
        where = entry.get("where", "")
        mapping_type = entry.get("mapping_type", "")
        if not isinstance(review_id, str) or not review_id.strip():
            raise ValueError("Each appendix comment entry needs a non-empty string 'id'.")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Each appendix comment entry needs a non-empty string 'title'.")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("Each appendix comment entry needs a non-empty string 'body'.")
        if not isinstance(where, str):
            raise ValueError("Each appendix comment entry 'where' must be a string.")
        if not isinstance(mapping_type, str):
            raise ValueError("Each appendix comment entry 'mapping_type' must be a string.")

        item = (
            r"\item \textbf{"
            + escape_latex_text(review_id)
            + r"} - \textbf{"
            + escape_latex_text(title)
            + r"}\\"
            + escape_latex_text(body)
        )
        meta_parts = []
        if mapping_type.strip():
            meta_parts.append("Mapping: " + mapping_type.strip())
        if where.strip():
            meta_parts.append("Visible in: " + where.strip())
        if meta_parts:
            item += r"\\{\footnotesize " + escape_latex_text(" | ".join(meta_parts)) + r"}"
        blocks.append(item)

    blocks.append(r"\end{itemize}")
    appendix_tex = "\n".join(blocks) + "\n"

    for marker in (r"\section{ACKNOWLEDGMENT}", r"\bibliographystyle{IEEEtran}"):
        if marker in diff_tex:
            return diff_tex.replace(marker, appendix_tex + marker, 1)

    raise RuntimeError("Could not find a safe insertion point for the review appendix.")


def append_once(text: str, needle: str, addition: str) -> str:
    if needle not in text:
        raise RuntimeError(f"Annotation target was not found in diff TeX: {needle}")
    return text.replace(needle, needle + addition, 1)


def apply_review_annotations(output_tex: Path, review_map: Path) -> list[str]:
    diff_tex = output_tex.read_text(encoding="utf-8")

    payload: dict[str, Any] = json.loads(review_map.read_text(encoding="utf-8"))
    entries = payload.get("annotations")
    if not isinstance(entries, list):
        raise ValueError("Review map must define an 'annotations' list.")

    diff_tex = insert_annotation_preamble(diff_tex)

    applied: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each annotation entry must be an object.")
        target = entry.get("target")
        review_id = entry.get("id", "")
        title = entry.get("title") or entry.get("label")
        body = entry.get("body", "")
        if not isinstance(review_id, str):
            raise ValueError("Each annotation entry 'id' must be a string.")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Each annotation entry needs a non-empty string 'title' or 'label'.")
        if not isinstance(target, str) or not target:
            raise ValueError("Each annotation entry needs a non-empty string 'target'.")
        if not isinstance(body, str):
            raise ValueError("Each annotation entry 'body' must be a string.")

        diff_tex = append_once(diff_tex, target, comment_macro(entry))
        applied.append(review_id or title)

    diff_tex = append_review_appendix(diff_tex, payload)
    output_tex.write_text(diff_tex, encoding="utf-8")
    return applied


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
    review_map = None
    if args.annotated_review_comments:
        if not args.review_map:
            raise ValueError("--annotated-review-comments requires --review-map.")
        review_map = resolve_input(args.review_map, project_dir)
        validate_review_map(review_map)

    default_name = (
        default_annotated_output_name(old_file, new_file)
        if args.annotated_review_comments
        else default_output_name(old_file, new_file)
    )
    output_name = args.output_name or default_name
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
    if review_map is not None:
        print(f"Review map: {review_map}")
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

    if args.annotated_review_comments and review_map is not None and not args.dry_run:
        applied = apply_review_annotations(output_tex, review_map)
        print(f"Applied {len(applied)} reviewer annotations.")

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
