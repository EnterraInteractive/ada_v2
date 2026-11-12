# Knowledge Galaxy Notes

Place your Markdown notes in this directory. The Knowledge Galaxy recursively indexes Markdown files here and stores voice/typed captures in `captures/`.

You may instead set the `ADA_NOTES_DIR` environment variable to an absolute notes-folder path before launching Ada. The configured notes directory is read for indexing; only the `captures/` subfolder is written by the Remember feature.

The Anthropic credential file is generated at the Ada project root as `config.json` on first backend launch. It is excluded from Git and blocked from Vite's browser file server. Add your API key to that local file yourself.
