import os
import re
import shutil
import subprocess
from pathlib import Path

MAIN_TEX = "main.tex"


def detect_main_tex(directory="."):
    tex_files = list(Path(directory).glob("*.tex"))
    candidates = []

    for tex_file in tex_files:
        score = 0
        with open(tex_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            if "\\documentclass" in content:
                score += 10
            if "\\begin{document}" in content:
                score += 5
            score += content.count("\\input{") + content.count("\\include{")
        candidates.append((score, tex_file))

    if not candidates:
        raise FileNotFoundError("No .tex files found in the directory.")

    candidates.sort(reverse=True)  # highest score first
    return str(candidates[0][1])


def flatten_tex(file_path, visited=None):
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


def extract_macros(tex_lines):
    macros = {}
    pattern = re.compile(r"\\newcommand\s*{\\(\w+)}(?:\[(\d+)\])?\s*{(.+)}")

    for line in tex_lines:
        match = pattern.match(line.strip())
        if match:
            name, num_args, body = match.groups()
            num_args = int(num_args) if num_args else 0
            macros[name] = {"args": num_args, "body": body}
    return macros


def apply_macros(tex_lines, macros):
    def replace_macros(line):
        for name, macro in macros.items():
            args = macro["args"]
            body = macro["body"]

            if args == 0:
                line = re.sub(rf"\\{name}\b", re.escape(body), line)
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


def collect_images(tex_lines):
    image_paths = set()
    for line in tex_lines:
        matches = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{(.+?)\}", line)
        for match in matches:
            image_paths.add(match)
    return image_paths


def convert_to_markdown(tex_file, md_file):
    subprocess.run(
        ["pandoc", tex_file, "-o", md_file, "--from=latex", "--to=gfm", "--mathjax"],
        check=True,
    )


def engrave_section_tag(tex_document):
    return re.sub(r"(\\section\{)", r"#<SECTIONMARK>#\1", tex_document)


def tex_preprocess_for_markdown_conversion(tex_document):
    # pandoc cannot work with documentclass
    if tex_document.startswith("\\documentclass"):
        return "\n".join(tex_document.split("\n")[1:])
    return tex_document


def remove_figures(tex_content):
    # Remove all content within \begin{figure} ... \end{figure}
    return re.sub(r"\\begin{figure}.*?\\end{figure}", "", tex_content, flags=re.DOTALL)


def remove_comments(tex_content):
    return "\n".join(
        [line for line in tex_content.split("\n") if not line.startswith("%")]
    )


def main(arxiv_id):
    main_tex = detect_main_tex(
        directory=f"/Users/baek/project/chavrusa/arxiv_module/paper_retriever/papers_root/{arxiv_id}/latex"
    )
    # print(f"📄 Detected main TeX file: {main_tex}")
    raw_tex_lines = flatten_tex(main_tex)

    main_tex = "".join(raw_tex_lines)
    main_tex = engrave_section_tag(main_tex)

    ############ LaTex -> KaTeX/MathJax ############
    # \label{subs:estimate semigroup}
    # \ref{subs:estimate semigroup}

    main_tex = re.sub(r"\\mathds", r"\\mathbb", main_tex)
    main_tex = re.sub(r"\\label\{(.+?)\}", "", main_tex)
    main_tex = re.sub(r"\\ref\{(.+?)\}", "", main_tex)

    # TODO:
    main_tex = remove_figures(main_tex)

    # main_tex = tex_preprocess_for_markdown_conversion(main_tex)

    ############ macro workaround ############
    # macros = extract_macros(raw_tex_lines)
    # expanded_tex = apply_macros(raw_tex_lines, macros)

    # expanded_tex = [re.sub(r'\\newcommand(.+)?\n', '', line) for line in expanded_tex ]
    # expanded_tex = [re.sub(r'\\renewcommand(.+)?\n', '', line) for line in expanded_tex ]

    # flat_file = "flattened_main_expanded.tex"
    # with open(flat_file, "w", encoding="utf-8") as f:
    #     f.writelines(expanded_tex)

    FLATTEN_TEX_DIR = "flattened"
    os.makedirs(FLATTEN_TEX_DIR, exist_ok=True)
    flat_file = os.path.join(FLATTEN_TEX_DIR, f"flattened_main_{arxiv_id}.tex")
    with open(flat_file, "w", encoding="utf-8") as f:
        f.writelines(main_tex)

    image_paths = collect_images(main_tex)
    os.makedirs("images", exist_ok=True)
    for img in image_paths:
        for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
            src = Path(img + ext)
            if src.exists():
                shutil.copy(src, Path("images") / src.name)
                break

    MARKDOWN_DIR = "markdown"
    os.makedirs(MARKDOWN_DIR, exist_ok=True)
    markdown_file_name = os.path.join(MARKDOWN_DIR, f"output_{arxiv_id}.md")

    convert_to_markdown(flat_file, markdown_file_name)
    # print("✅ Conversion complete: `output.md`")

    with open(markdown_file_name, "r", encoding="utf-8") as f:
        markdown_file = f.read()

    ############ Misc postprocess ############
    markdown_file = re.sub(r"\*\$\$", "$$", markdown_file)
    markdown_file = re.sub(r"\$\$\*", "$$", markdown_file)
    markdown_file = re.sub(r"\\vvvert", r"\\|", markdown_file)
    markdown_file = re.sub("◻", "\n$" + r"\\boxed" + "{}$", markdown_file)
    markdown_file = re.sub("$$", "\n$$\n", markdown_file)

    with open(markdown_file_name, "w", encoding="utf-8") as f:
        f.write(markdown_file)


if __name__ == "__main__":
    # arxiv_id = "2503.13551"   # clear
    # arxiv_id = "2406.11944"
    # main(arxiv_id)
    papers_dir = "paper_sources"
    for arxiv_id in os.listdir(papers_dir):
        if re.search(r"^\d\d\d\d\.\d\d\d\d\d$", arxiv_id) is None:
            continue
        try:
            main(arxiv_id)
        # time.sleep(5)
        except Exception:
            pass

    #     #     import pdb
    #     #     from pprint import pprint
    #     #     def cls():
    #     #         print("\n"*100)
    #     #     print(e)
    #     #     pdb.set_trace()
