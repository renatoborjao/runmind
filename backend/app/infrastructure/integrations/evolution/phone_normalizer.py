class PhoneNormalizer:

    @staticmethod
    def normalize(
        raw_jid: str,
    ) -> str:

        phone = raw_jid.split("@")[0]

        phone = phone.replace(
            "+",
            "",
        ).replace(
            " ",
            "",
        ).replace(
            "-",
            "",
        )

        return phone
