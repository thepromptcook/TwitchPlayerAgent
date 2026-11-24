import asyncio
import io

from twitchplayeragent.chat import ChatMessage, StdinChat, parse_irc_line


def test_parse_irc_privmsg():
    line = ("@badge-info=;color=#FF0000;display-name=AshKetchum;mod=0 "
            ":ashketchum!ashketchum@ashketchum.tmi.twitch.tv PRIVMSG #tpp :up2left")
    m = parse_irc_line(line)
    assert m == ChatMessage("ashketchum", "AshKetchum", "up2left")
    assert parse_irc_line(":tmi.twitch.tv 001 justinfan1 :Welcome") is None


def test_stdin_chat_reads_lines_and_skips_comments(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("# comment\n\nash: up\nA\n"))

    async def collect():
        return [m async for m in StdinChat()]

    assert asyncio.run(collect()) == [ChatMessage("ash", "ash", "up"), ChatMessage("you", "you", "A")]
