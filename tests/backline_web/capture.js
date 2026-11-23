// SPDX-FileCopyrightText: 2026 Brad Barnett
//
// SPDX-License-Identifier: MIT

// Records what a page plays through Web Audio, for test_backline_web.py.
// Every AudioContext's destination is swapped for a gain node that feeds
// the real one and a recorder, so whatever the page connects to its
// destination is captured as it plays. backlineCapture() returns the left
// channel so far as 16-bit PCM in base64, with the context's rate.
(() => {
  const real = Object.getOwnPropertyDescriptor(BaseAudioContext.prototype, "destination").get;
  const WORKLET = `
    class Capture extends AudioWorkletProcessor {
      constructor() { super(); this.buf = new Float32Array(4096); this.n = 0; }
      process(inputs) {
        const ch = inputs[0] && inputs[0][0];
        if (ch) {
          for (let i = 0; i < ch.length; i++) {
            this.buf[this.n++] = ch[i];
            if (this.n === this.buf.length) { this.port.postMessage(this.buf); this.buf = new Float32Array(4096); this.n = 0; }
          }
        }
        return true;
      }
    }
    registerProcessor("backline-capture", Capture);`;
  const chunks = [];
  let rate = 0;
  Object.defineProperty(BaseAudioContext.prototype, "destination", {
    configurable: true,
    get() {
      if (!this.__tap) {
        const dest = real.call(this);
        const tap = this.createGain();
        tap.connect(dest);
        rate = this.sampleRate;
        // An AudioWorklet records on the audio thread: a ScriptProcessor
        // waits on the page's busy main thread and stalls the graph.
        const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
        this.audioWorklet.addModule(url).then(() => {
          const recorder = new AudioWorkletNode(this, "backline-capture", { numberOfOutputs: 0 });
          recorder.port.onmessage = (e) => chunks.push(e.data);
          tap.connect(recorder);
        });
        this.__tap = tap;
      }
      return this.__tap;
    },
  });
  window.backlineCapture = () => {
    let n = 0;
    for (const c of chunks) n += c.length;
    const pcm = new Int16Array(n);
    let at = 0;
    for (const c of chunks) {
      for (let i = 0; i < c.length; i++) pcm[at++] = Math.max(-32768, Math.min(32767, Math.round(c[i] * 32767)));
    }
    let text = "";
    const bytes = new Uint8Array(pcm.buffer);
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { rate, pcm: btoa(text) };
  };
})();
