class PcmProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions.targetRate;
    this.phase = 0;
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || !channels.length) return true;
    const frameCount = channels[0].length;
    const mono = new Float32Array(frameCount);
    for (let channel = 0; channel < channels.length; channel += 1) {
      const samples = channels[channel];
      for (let index = 0; index < frameCount; index += 1) mono[index] += samples[index] / channels.length;
    }
    const ratio = sampleRate / this.targetRate;
    const output = [];
    while (this.phase < frameCount) {
      const value = Math.max(-1, Math.min(1, mono[Math.floor(this.phase)]));
      output.push(value < 0 ? value * 0x8000 : value * 0x7fff);
      this.phase += ratio;
    }
    this.phase -= frameCount;
    if (output.length) {
      const pcm = Int16Array.from(output);
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-processor", PcmProcessor);
