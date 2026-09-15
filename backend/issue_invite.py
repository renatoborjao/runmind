"""Gera um código de convite pro auto-cadastro no app (acesso fechado). Só quem
tem um código consegue criar conta enquanto o público é baixo.

    cd ~/runmind/backend && .venv/bin/python issue_invite.py [opções]

Opções:
    --label "amigos da corrida"   rótulo livre (só pra você lembrar)
    --uses 5                      nº máximo de cadastros (padrão: 1)
    --days 30                     validade em dias (padrão: sem expirar)

Exemplos:
    .venv/bin/python issue_invite.py                      # 1 uso, não expira
    .venv/bin/python issue_invite.py --uses 10 --days 14  # 10 usos, 2 semanas
"""

import argparse

from app.infrastructure.persistence.invite_code_repository import (
    InviteCodeRepository,
)


def main() -> None:

    parser = argparse.ArgumentParser(description="Gera código de convite Ritmind")

    parser.add_argument("--label", default="", help="rótulo livre")

    parser.add_argument(
        "--uses",
        type=int,
        default=1,
        help="nº máximo de cadastros (padrão: 1; 0 = ilimitado)",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="validade em dias (padrão: sem expirar)",
    )

    args = parser.parse_args()

    max_uses = None if args.uses == 0 else args.uses

    code = InviteCodeRepository().issue(
        label=args.label,
        max_uses=max_uses,
        ttl_days=args.days,
    )

    uses_txt = "ilimitado" if max_uses is None else f"{max_uses} uso(s)"

    days_txt = "não expira" if args.days is None else f"expira em {args.days} dia(s)"

    print("=" * 44)
    print(f"  Código de convite:  {code}")
    print(f"  {uses_txt} · {days_txt}")
    if args.label:
        print(f"  Rótulo: {args.label}")
    print("=" * 44)
    print("  Mande pro atleta abrir o app > Criar conta.")


if __name__ == "__main__":

    main()
