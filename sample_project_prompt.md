Please read `AGENTS.md` to understand your strict operating directives and environment constraints. We are building a new project called `agentic-video-inspector`.

**Project Goal:** Build a robust, memory-efficient Python application that accepts either an Internet Archive video URL OR a direct video file upload. It will extract the audio, chunk-transcribe it to stay under 6GB of RAM, and generate a summary using a local LLM.

**Test Asset:** You must use this exact Internet Archive URL for URL-based testing: `https://archive.org/details/sotn2026`

**Execution Directive (Full Autonomy):** You must act fully autonomously as a Senior Software Engineer. You must string together as many development cycles as necessary to finish this project end-to-end. Do NOT stop to ask me for permission to proceed to the next phase. You are only authorized to halt execution and await my input if:
1. You hit an unresolvable OS/dependency blocker that you cannot fix after multiple analytical troubleshooting attempts and online searches.
2. The project is 100% complete and the Final Report is generated.

**Reporting Directive:** To prove your progress, you MUST generate a `docs/development_cycle_X.md` file at the exact moment you finish each Phase below. Write the file, commit your changes, and then immediately begin the next Phase without stopping your response.

---

### Phase 1: Core Foundation & Ingestion
1. **Environment Setup:** You have a `src/agentic_video_inspector/` package and `logs/` folder initialized. Run `uv add` to install: `yt-dlp`, `faster-whisper`, `openai`, `python-dotenv`, `gradio`, `pytest`, and `pydub`.
2. **URL Extraction:** Inside `src/agentic_video_inspector/`, write logic to use `yt-dlp` to download audio from the `archive.org` test URL. (No YouTube bypasses are needed).
3. **File Upload Validator:** Write logic to handle direct file uploads. It MUST verify that the file extension is strictly `.mp4` or `.mov`. It MUST verify the file size is strictly under 500MB. Raise clear ValueError exceptions if these fail.
*Requirement:* Write `pytest` scripts in the `tests/` directory to verify both ingest methods. Generate `docs/development_cycle_1.md` and proceed.

### Phase 2: Memory-Safe Transcription (6GB RAM Limit)
1. **Audio Chunking:** Loading massive audio files into AI models will crash our container. Check the audio duration. If it exceeds 10 minutes, use `pydub` to slice it into <=10-minute temporary chunks.
2. **Sequential Processing:** Initialize `faster-whisper` (`device="cpu"`, `compute_type="int8"`). Process the chunks sequentially.
3. **Memory Management (CRITICAL):** You must actively manage memory. After transcribing a chunk, you must explicitly delete the chunk variable (`del chunk`) and force garbage collection (`import gc; gc.collect()`) to ensure RAM never spikes above 6GB. Append the results to a final transcript string.
*Requirement:* Write tests to verify chunking and transcription. Generate `docs/development_cycle_2.md` and proceed.

### Phase 3: Dynamic LLM Summarization
1. **LLM Connection:** Use the `openai` Python package to summarize the transcript.
2. **Dynamic Config:** You must NOT hardcode the LLM URL or model name. Use `python-dotenv` to dynamically load `LLM_BASE_URL` and `LLM_MODEL_NAME` from the auto-injected `.env` file.
3. **Token Safety (Map-Reduce):** If the transcript is massive, chunk the text, summarize the chunks individually, and then summarize the combined summaries to avoid blowing out the LLM context window.
4. **Artifacts:** Save the final transcript and summary to `artifacts/` with a datetime stamp.
*Requirement:* Write tests mocking the LLM response. Generate `docs/development_cycle_3.md` and proceed.

### Phase 4: Gradio UI & Programmatic Testing
1. **The UI:** Create `src/agentic_video_inspector/app.py`. It needs two input tabs: one for the URL, and one for a drag-and-drop File component. Include a "Generate" button and text areas for the transcript and summary outputs.
2. **Server Binding:** Bind the server to `server_name="0.0.0.0"` and dynamically load `APP_PORT` from the `.env` file (fallback to 7860).
3. **Programmatic Test:** Launch the app in the background (`> logs/app.log 2>&1 &`). Write `tests/test_ui.py` using `gradio_client` to programmatically submit the test URL and assert it receives the outputs.
4. **Port Cleanup:** Kill the background server holding the port (`sudo fuser -k 7860/tcp`) after the test completes.
*Requirement:* Run the UI tests. Generate `docs/development_cycle_4.md` and proceed.

### Phase 5: Final Handoff
Refer to the `The Final Handoff & Reporting` section of your `AGENTS.md` file. Install `cloc` via apt-get, generate your `docs/final_report.md` (include the pytest terminal output as proof of success), update the `README.md`, and safely halt.
