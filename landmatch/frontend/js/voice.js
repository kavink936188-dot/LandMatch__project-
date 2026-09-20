/* Voice input (Web Speech API) + optional read-aloud. Works best in Chrome / Edge / Android. */
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

/**
 * initVoice({ button, langSelect, onText, onState })
 *  - button:     the mic <button>
 *  - langSelect: optional <select> whose value is a BCP-47 tag (en-IN, ta-IN, hi-IN)
 *  - onText(t):  called with the recognised sentence
 *  - onState(s): called with short status messages for the UI
 */
function initVoice({ button, langSelect, onText, onState = () => {} }) {
  if (!SpeechRec) {
    button.disabled = true;
    button.title = "Voice input is not supported in this browser. Try Chrome or Edge.";
    onState("Voice input needs Chrome or Edge.");
    return null;
  }
  const rec = new SpeechRec();
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  let listening = false;

  button.addEventListener("click", () => {
    if (listening) { rec.stop(); return; }
    rec.lang = langSelect ? langSelect.value : "en-IN";
    try { rec.start(); } catch (e) { /* already started */ }
  });
  rec.onstart = () => { listening = true; button.classList.add("listening"); button.setAttribute("aria-pressed", "true"); onState("Listening… speak now"); };
  rec.onend = () => { listening = false; button.classList.remove("listening"); button.setAttribute("aria-pressed", "false"); };
  rec.onerror = e => {
    const msg = { "not-allowed": "Microphone access is blocked. Allow it in the browser address bar.",
                  "no-speech": "Didn't catch that. Tap the mic and try again.",
                  "network": "Voice recognition needs an internet connection." }[e.error] || "Voice error: " + e.error;
    onState(msg);
  };
  rec.onresult = e => {
    const text = e.results[0][0].transcript.trim();
    onState(`Heard: “${text}”`);
    if (text) onText(text);
  };
  return rec;
}

function speak(text, lang = "en-IN") {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang;
  window.speechSynthesis.speak(u);
}
