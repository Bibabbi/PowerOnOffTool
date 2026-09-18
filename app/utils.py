def command_to_bytes(command: str) -> bytes:
    replacements = {
        "\\r": "\r",
        "\\n": "\n",
        "\\t": "\t",
        "\\\\": "\\",
    }
    for text, control_char in replacements.items():
        command = command.replace(text, control_char)
    return command.encode("utf-8")
