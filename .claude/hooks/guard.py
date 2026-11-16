"""Trava do Claude Code no Ritmind (hook PreToolUse) — custa zero token: só lê o comando antes
de ele rodar e bloqueia o que as regras do dono proíbem:

  - `git add -A`, `git add .`, `git add --all`, `git commit -a`: commit só com caminhos explícitos
    (há arquivos soltos na pasta que não podem subir);
  - escrever em `backend/storage` no PC: dado de atleta só mora na VM.

Saída 2 = bloqueia e o motivo volta pro Claude. Qualquer erro aqui deixa passar (a trava nunca
trava o trabalho por defeito próprio)."""

import json
import re
import sys

GIT_ADD_ALL = re.compile(r"\bgit\s+add\s+(?:[^|;&]*\s)?(?:-A|--all|\.)(?=\s|$|[;&|])")
GIT_COMMIT_ALL = re.compile(r"\bgit\s+commit\s+(?:[^|;&]*\s)?-(?:a|am|[a-z]*a[a-z]*)\b")
STORAGE = re.compile(r"backend[\\/]+storage(?:[\\/]|$)", re.IGNORECASE)


def main() -> int:

    try:

        event = json.load(sys.stdin)

    except Exception:

        return 0

    tool = event.get("tool_name", "")

    data = event.get("tool_input") or {}

    if tool in ("Bash", "PowerShell"):

        command = str(data.get("command", ""))

        # o comando de fato, sem o corpo de heredoc nem o texto entre aspas (uma mensagem de commit
        # que CITA "git add -A" não é um git add -A)
        bare = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\1\b", " ", command, flags=re.DOTALL)

        bare = re.sub(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"", " ", bare)

        if GIT_ADD_ALL.search(bare) or GIT_COMMIT_ALL.search(bare):

            print(
                "Bloqueado pela trava do projeto: commit só com caminhos explícitos "
                "(git add <arquivo> <arquivo>). Há arquivos soltos na pasta que não podem subir.",
                file=sys.stderr,
            )

            return 2

        # o storage como DESTINO da escrita (não só citado num texto): `> backend/storage/…`,
        # `tee|cp|mv|mkdir|Out-File|Set-Content … backend/storage`
        target = re.search(
            r"(?:>>?\s*[\"']?|\b(?:tee|cp|mv|mkdir|Out-File|Set-Content|New-Item)\b[^|;&\n]*\s[\"']?)"
            r"[^\s\"']*backend[\\/]+storage",
            command,
            re.IGNORECASE,
        )

        if target:

            print(
                "Bloqueado pela trava do projeto: nada de escrever em backend/storage no PC — dado "
                "de atleta só na VM.",
                file=sys.stderr,
            )

            return 2

    if tool in ("Write", "Edit", "NotebookEdit"):

        path = str(data.get("file_path") or data.get("notebook_path") or "")

        if STORAGE.search(path):

            print(
                "Bloqueado pela trava do projeto: nada de escrever em backend/storage no PC — dado "
                "de atleta só na VM.",
                file=sys.stderr,
            )

            return 2

    return 0


if __name__ == "__main__":

    sys.exit(main())
