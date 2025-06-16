import os
import re
import subprocess
from pathlib import Path
from typing import List

MARKDOWN_DIR = "markdown"
FLATTEN_TEX_DIR = "flattened"
SECTIONS_DIR = "sections"
PAPER_DIRS = "paper_sources"


def search_section_by_between_begin_end(tex_doc):
    """
    - begin을 만나면 stack 시작
    - end을 만나면 pop
    - 현재 level 파악

    - section 만나면 다음 section의 시작을 파악하여 현재 section 구분해냄.
    - 다음 section이 존재하지 않으면 마지막 section이라고 판별
    - 마지막 section에서 (nested) begin end 구문 안에 들어가 있으면 end 구분 제거해냄.

    """
    stack = []
    final_found = None
    sections = []
    for found in re.finditer(r"\\begin{.+?}|\\end{.+?}|\\section{", tex_doc):
        if "begin" in found.group():
            stack.append(found)
        elif "end" in found.group():
            # 마지막 section에서 end 제거
            # 현재 크게 두가지 경우 250604 15:17
            # 1. begin document으로 시작... 맨 마지막에 seciton 등장해서 자름. 그리고 end document 등장하여 없애야 하는 경우
            # 2. begin document으로 시작... 맨 마지막에 seciton 등장해서 자름. 그리고 section 안에 begin 다시 등장하여 이 begin의 end 마주함. 살려야 함.
            if final_found is not None:
                # 1의 경우
                if "end{document}" in found.group():
                    section_partial = tex_doc[final_found.start() : found.start()]
                    sections.append(section_partial)
                    return [section.strip() for section in sections]

                # 2의 경우
                # 어떻게 구분하는가? begin이 section 안에서 등장했는가, 바깥에서 등장했는가?
                begin_found = stack[-1]
                begin_found.start()  # begin 시작 위치
                final_found.start()  # 마지막 section 시작 위치

                if begin_found.start() < final_found.start():
                    # 현재 마주한 begin-end가 현재(마지막) section 보다 앞서서 시작 됨. e.g. end{document} 등...
                    section_partial = tex_doc[
                        final_found.start() : found.start()
                    ]  # end{document} 제외하여 자름
                    sections.append(section_partial)
                    return [section.strip() for section in sections]

                # else: # 그렇지 않으면 계속 살려야 함. 언제까지? 바로 위의 경우처럼 begin-end가 현재 마지막 section 보다 앞서서 실행되었을 경우까지 그냥 냅둠.
            try:
                stack.pop()
            except Exception as e:
                raise Exception(f"error: {e}\nissue: {found.group()}")
        else:
            # print(f"section found in begin end depth {len(stack)}")
            found_next = list(re.finditer(r"\\section{", tex_doc[found.end() :]))
            if found_next:
                section_partial = tex_doc[
                    found.start() : len(tex_doc[: found.end()])
                    + found_next[0].start() :
                ]
                sections.append(section_partial)
            else:  # 마지막 section. 다음 \\section을 찾을 수 없다.
                # found: 마지막 section이 포함되어 있다. 그리고 begin end가 끝나지 않고 있을 수 있다.
                final_found = found
    return [section.strip() for section in sections]


def search_table_begin_end(tex_doc):
    stack = []
    before_index = 0
    new_tex_doc = ""
    for found in re.finditer(r"\\begin{tab.+?}|\\end{tab.+?}", tex_doc):
        if "begin" in found.group():
            stack.append(found)
        elif "end" in found.group():
            begin = stack.pop()

            # table 안에 tabular nested 될 수 있음.
            # 가장 바깥 table에서만 지운다.
            if not stack:
                end = found
                before_string = tex_doc[before_index : begin.start()]
                new_tex_doc += before_string

                before_index = end.end() + 1
    new_tex_doc += tex_doc[before_index:]
    return new_tex_doc


def search_itemize_begin_end(tex_doc):
    stack = []
    before_index = 0
    new_tex_doc = ""
    for found in re.finditer(r"\\begin{itemize.*?}|\\end{itemize.*?}", tex_doc):
        if "begin" in found.group():
            stack.append(found)
        elif "end" in found.group():
            begin = stack.pop()

            # itemize 안에 itemize에서만 nested 될 수 있음.
            # 가장 바깥 itemize에서만 지운다.
            if not stack:
                end = found
                before_string = tex_doc[before_index : begin.start()]
                new_tex_doc += before_string

                before_index = end.end() + 1
    new_tex_doc += tex_doc[before_index:]
    return new_tex_doc


def detect_main_tex(directory: str = "."):
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
    # new flatten starts with newline. comments may corrupts without newlines
    output = ["\n"]

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


def convert_to_markdown(tex_file: str, md_file: str):
    subprocess.run(
        ["pandoc", tex_file, "-o", md_file, "--from=latex", "--to=gfm", "--mathjax"],
        check=True,
    )


def remove_figures(tex_content: str) -> str:
    # Remove all content within \begin{figure} ... \end{figure}
    # figure 뒤에 별 있을 수 있음.
    return re.sub(
        r"\\begin{figure.*?\\end{figure\*?}", "", tex_content, flags=re.DOTALL
    )


def remove_comments(tex_lines: List[str]) -> str:
    return [
        re.sub(r"(?<!\\)%.*", "", line).strip()
        if re.search(r"(?<!\\)%.*", line)
        else line
        for line in tex_lines
    ]


def convert_2_markdown(arxiv_id, flat_file: str, file_name: str) -> None:
    arxiv_md_path = os.path.join(MARKDOWN_DIR, arxiv_id)
    os.makedirs(arxiv_md_path, exist_ok=True)
    markdown_file_name = os.path.join(arxiv_md_path, file_name)

    convert_to_markdown(flat_file, markdown_file_name)

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


def save_tex_sections(arxiv_id: str, sections: List[str]):
    for s_i, section in enumerate(sections):
        sections_arxiv_path = os.path.join(SECTIONS_DIR, arxiv_id)
        save_tex(section, sections_arxiv_path, f"section_{s_i}.tex")


def convert_sections(arxiv_id: str):
    sections_arxiv_path = os.path.join(SECTIONS_DIR, arxiv_id)
    for s_i, file_path in enumerate(os.listdir(sections_arxiv_path)):
        convert_2_markdown(
            arxiv_id,
            os.path.join(sections_arxiv_path, file_path),
            f"output_{arxiv_id}_{s_i}.md",
        )


def convert_tex(arxiv_id):
    """"""
    flat_arxiv_path = os.path.join(FLATTEN_TEX_DIR, arxiv_id)
    convert_2_markdown(
        arxiv_id,
        os.path.join(flat_arxiv_path, "cleanse_tex.tex"),
        f"output_{arxiv_id}_cleanse.md",
    )


def save_tex(tex_doc: str, file_path: str, file_name: str):
    os.makedirs(file_path, exist_ok=True)
    with open(os.path.join(file_path, file_name), "w", encoding="utf-8") as f:
        f.write("".join(tex_doc))


def prep_tex(arxiv_id: str, verbose: bool = False):
    main_tex = detect_main_tex(directory=f"{PAPER_DIRS}/{arxiv_id}/latex")
    if verbose:
        print(f"📄 Detected main TeX file: {main_tex}")
    raw_tex_lines = flatten_tex(main_tex)

    raw_tex_lines = remove_comments(raw_tex_lines)

    flatten_arxiv_path = os.path.join(FLATTEN_TEX_DIR, arxiv_id)
    save_tex("".join(raw_tex_lines), flatten_arxiv_path, "flatten_tex.tex")

    ############ macro workaround ############
    macros = extract_macros(raw_tex_lines)
    raw_tex_lines = remove_macros(raw_tex_lines)
    expanded_tex_lines = apply_macros(raw_tex_lines, macros)

    macro_tex = "".join(expanded_tex_lines)

    save_tex(macro_tex, flatten_arxiv_path, "macro_tex.tex")

    ############ LaTex -> KaTeX/MathJax ############
    # \label{subs:estimate semigroup}
    # \ref{subs:estimate semigroup}
    cleanse_tex = re.sub(r"\\mathds", r"\\mathbb", macro_tex)
    cleanse_tex = re.sub(r"\\label\{(.+?)\}", "", cleanse_tex)
    cleanse_tex = re.sub(r"\\ref\{(.+?)\}", "", cleanse_tex)
    cleanse_tex = re.sub(r"\n+\}", "\n}", macro_tex)

    # TODO: restore figure to convert
    cleanse_tex = remove_figures(cleanse_tex)

    ############ image workaround ############
    # image_paths = collect_images(cleanse_tex)
    # os.makedirs("images", exist_ok=True)
    # for img in image_paths:
    #     for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
    #         src = Path(img + ext)
    #         if src.exists():
    #             shutil.copy(src, Path("images") / src.name)
    #             break

    # TODO restore table
    cleanse_tex = search_table_begin_end(cleanse_tex)
    # TODO itemize table
    cleanse_tex = search_itemize_begin_end(cleanse_tex)

    # # final post process
    # # last line must be end document. no additional cahr or new line is valid.
    # cleanse_tex = cleanse_tex.strip()

    save_tex(cleanse_tex, flatten_arxiv_path, "cleanse_tex.tex")
    return cleanse_tex


if __name__ == "__main__":
    arxiv_id = "2505.24341v1"
    main_tex = prep_tex(arxiv_id)
    sections = search_section_by_between_begin_end(main_tex)
    save_tex_sections(arxiv_id, sections)
    convert_tex(arxiv_id)
