import os
import re
import subprocess
from pathlib import Path
from typing import List

MARKDOWN_DIR = "markdown"
FLATTEN_TEX_DIR = "flattened"
PAPER_DIRS = "paper_sources"


def detect_main_tex(directory: str="."):
    tex_files = list(Path(directory).glob("*.tex"))
    candidates = []

    for tex_file in tex_files:
        score = 0
        with open(tex_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            if "\\documentclass" in content:
                score += 100
            if "\\begin{document}" in content:
                score += 50

            score += len(re.findall(r"\\section", content))
            score += len(re.findall(r"\\subsection", content))
            score += content.count("\\input{") * 10 + content.count("\\include{") * 10
        candidates.append((score, tex_file))

    if not candidates:
        raise FileNotFoundError("No .tex files found in the directory.")
    candidates.sort(reverse=True)  # highest score first
    return str(candidates[0][1])


def flatten_tex(file_path: str, visited: bool = None) -> List[str]:
    visited = visited or set()
    output = []

    if file_path in visited:
        return []
    visited.add(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = re.search(r"\\(input|include)\{(.+?)\}", line)
            if match:
                _, include_path = match.groups()
                include_file = Path(file_path).parent / (include_path + ".tex")
                if include_file.exists():
                    output.extend(flatten_tex(str(include_file), visited))
                else:
                    output.append(f"% Could not find file: {include_path}.tex\n")
            else:
                output.append(line)
    return output


def extract_macros(tex_lines: List[str]) -> dict:
    macros = {}
    pattern = re.compile(
        r"\\(renewcommand|newcommand|DeclareMathOperator)\*?\s*{\\(\w+)}(?:\[(\d+)\])?\s*{(.+)}"
    )

    for line in tex_lines:
        match = pattern.match(line.strip())
        if match:
            _, name, num_args, body = match.groups()
            num_args = int(num_args) if num_args else 0
            macros[name] = {"args": num_args, "body": body}
    return macros


def remove_macros(tex_lines: List[str]):
    return [
        re.sub(
            r"\\(renewcommand|newcommand|DeclareMathOperator)\*?\s*{\\(\w+)}(?:\[(\d+)\])?\s*{(.+)}",
            "",
            line,
        )
        for line in tex_lines
    ]


def apply_macros(tex_lines, macros):
    def replace_macros(line):
        for name, macro in macros.items():
            args = macro["args"]
            body = macro["body"]

            if args == 0:
                line = re.sub(rf"\\{name}(?![a-zA-Z])", re.escape(body), line)
            else:
                # Match \name{arg1}{arg2}...
                pattern = rf"\\{name}" + r"(" + r"\s*\{(.*?)\}" * args + r")"

                def repl(m):
                    parts = [m.group(i) for i in range(2, 2 + args)]
                    result = body
                    for i, val in enumerate(parts, start=1):
                        result = result.replace(f"#{i}", val)
                    return result

                line = re.sub(pattern, repl, line)
        return line

    return [replace_macros(line) for line in tex_lines]


def collect_images(tex_lines: List[str]):
    image_paths = set()
    for line in tex_lines:
        matches = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{(.+?)\}", line)
        for match in matches:
            image_paths.add(match)
    return image_paths


def convert_to_markdown(tex_file:str, md_file:str):
    subprocess.run(
        ["pandoc", tex_file, "-o", md_file, "--from=latex", "--to=gfm", "--mathjax"],
        check=True,
    )


def remove_figures(tex_content: str) -> str:
    # Remove all content within \begin{figure} ... \end{figure}
    return re.sub(r"\\begin{figure}.*?\\end{figure}", "", tex_content, flags=re.DOTALL)


def remove_comments(tex_lines: List[str]) -> str:
    return [re.sub(r"(?<!\\)%.*", "", line) for line in tex_lines]


def convert_2_markdown(flat_file: str, file_name: str) -> None:
    os.makedirs(MARKDOWN_DIR, exist_ok=True)
    markdown_file_name = os.path.join(MARKDOWN_DIR, file_name)

    convert_to_markdown(flat_file, markdown_file_name)
    # print("✅ Conversion complete: `output.md`")

    ############ Misc postprocess ############
    with open(markdown_file_name, "r", encoding="utf-8") as f:
        markdown_file = f.read()
    markdown_file = re.sub(r"\*\$\$", "$$", markdown_file)
    markdown_file = re.sub(r"\$\$\*", "$$", markdown_file)
    markdown_file = re.sub(r"\\vvvert", r"\\|", markdown_file)
    markdown_file = re.sub("◻", "\n$" + r"\\boxed" + "{}$", markdown_file)
    markdown_file = markdown_file.replace("$$", "\n$$\n")

    with open(markdown_file_name, "w", encoding="utf-8") as f:
        f.write(markdown_file)


def save_convert_sections(sections: List[str]):
    for s_i, section in enumerate(sections):
        os.makedirs(FLATTEN_TEX_DIR, exist_ok=True)
        section_file = os.path.join(
            FLATTEN_TEX_DIR, f"flattened_main_{arxiv_id}_{s_i}.tex"
        )
        with open(section_file, "w", encoding="utf-8") as f:
            f.writelines(section)

        convert_2_markdown(section_file, f"output_{arxiv_id}_{s_i}.md")


def prep_tex(arxiv_id: str, verbose: bool = True):
    main_tex = detect_main_tex(directory=f"{PAPER_DIRS}/{arxiv_id}/latex")
    if verbose:
        print(f"📄 Detected main TeX file: {main_tex}")
    raw_tex_lines = flatten_tex(main_tex)

    raw_tex_lines = remove_comments(raw_tex_lines)

    ############ macro workaround ############
    macros = extract_macros(raw_tex_lines)
    raw_tex_lines = remove_macros(raw_tex_lines)
    expanded_tex_lines = apply_macros(raw_tex_lines, macros)

    main_tex = "".join(expanded_tex_lines)
    # main_tex = engrave_section_tag(main_tex)

    with open("tmp.tex", "w", encoding="utf-8") as f:
        f.write(main_tex)

    ############ LaTex -> KaTeX/MathJax ############
    # \label{subs:estimate semigroup}
    # \ref{subs:estimate semigroup}
    main_tex = re.sub(r"\\mathds", r"\\mathbb", main_tex)
    main_tex = re.sub(r"\\label\{(.+?)\}", "", main_tex)
    main_tex = re.sub(r"\\ref\{(.+?)\}", "", main_tex)

    # TODO: restore figure
    main_tex = remove_figures(main_tex)

    ############ image workaround ############
    # image_paths = collect_images(main_tex)
    # os.makedirs("images", exist_ok=True)
    # for img in image_paths:
    #     for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
    #         src = Path(img + ext)
    #         if src.exists():
    #             shutil.copy(src, Path("images") / src.name)
    #             break

    return main_tex


def main(arxiv_id: str):
    main_tex = prep_tex(arxiv_id)

    ############ section split with section mark and pandoc ############
    # sections = main_tex.split("#<SECTIONMARK>#")[1:]
    # sections[-1] = sections[-1].replace("\end{document}", "")

    ############ section split with algotithm and pandoc ############
    from lab_begin_level_func import begin_end_searach

    sections = begin_end_searach(main_tex)
    save_convert_sections(sections)


if __name__ == "__main__":
    ## 전체 파일에 대하여
    # for arxiv_id in os.listdir(PAPER_DIRS):
    #     if re.search(r"^\d\d\d\d\.\d\d\d\d\d(v\d+)?$", arxiv_id) is None:
    #         continue
    #     try:
    #         main(arxiv_id)
    #     except Exception as e:
    #         print(e)
    #         pass

    # arxiv_id = "2411.09629"

    # 250610
    # pass. also calibrate the main tex. there is some sample texes which has documentclass,includes, begin document etc...
    # arxiv_id = "2506.01604v1"

    # TODO "2505.24838v1"
    arxiv_id = "2505.24838v1"
    main(arxiv_id)
