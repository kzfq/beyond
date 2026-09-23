RESET = "\u001b[0m"
BOLD = "\u001b[1m"
UNDERLINE = "\u001b[4m"

DARK = "\u001b[30m"
WHITE = "\u001b[0;37m"
CYAN = "\u001b[0;36m"
PURPLE = "\u001b[0;35m"
BLUE = "\u001b[0;34m"

NAME = "Beyond"
VERSION = "v0.1.0"
AUTHOR = "Nox"


def _block(content: str) -> str:
    lines = content.split("\n")
    result = ["> ```ansi"]
    for line in lines:
        result.append(f"> {line}")
    result.append("> ```")
    return "\n".join(result)


def header(subtitle: str) -> str:
    return _block(
        f"{PURPLE}{BOLD}{UNDERLINE}{NAME}{RESET}{DARK} :: {RESET}{WHITE}{VERSION}{DARK} :: {RESET}{BLUE}{subtitle}{RESET}"
    )


def category_list(categories: dict) -> str:
    lines = []
    for name, desc in categories.items():
        lines.append(f"{PURPLE}{name:<10}{DARK}:: {RESET}{WHITE}{desc}{RESET}")
    return _block("\n".join(lines))


def footer_main() -> str:
    return _block(f"{DARK}Developed by {WHITE}{AUTHOR}{RESET}")


def footer_page(prefix: str, category: str, page: int, total: int) -> str:
    return _block(f"{DARK}{prefix}help {category.lower()} [1-{total}]{RESET}")


def command_list(cmds: list) -> str:
    lines = []
    for name, desc in cmds:
        lines.append(f"{CYAN}{name:<13}{DARK}:: {RESET}{WHITE}{desc}{RESET}")
    return _block("\n".join(lines))


def command_usage(name: str, usage: str, description: str, prefix: str) -> str:
    title = f"{PURPLE}{BOLD}{UNDERLINE}{NAME}{RESET}{DARK} :: {RESET}{WHITE}{VERSION}{DARK} :: {RESET}{BLUE}{name.upper()}{RESET}"
    body = (
        f"{CYAN}{'Command':<13}{DARK}:: {RESET}{WHITE}{name}{RESET}\n"
        f"{CYAN}{'Usage':<13}{DARK}:: {RESET}{WHITE}{prefix}{usage}{RESET}\n"
        f"{CYAN}{'Description':<13}{DARK}:: {RESET}{WHITE}{description}{RESET}"
    )
    return _block(title) + "\n" + _block(body)


def success(msg: str) -> str:
    return f"> **{msg}**"


def error(msg: str) -> str:
    return f"> **{msg}**"


def warning(msg: str) -> str:
    return f"> **{msg}**"
