export class VideoStreamer {
    private videoElement: HTMLVideoElement | null = null;
    private canvasElement: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D | null;
    private timer: number | null = null;
    private stream: MediaStream | null = null;

    constructor() {
        this.canvasElement = document.createElement("canvas");
        // Gemini vision works well with moderately sized images, large ones crash the websocket
        this.canvasElement.width = 640;
        this.canvasElement.height = 360;
        this.ctx = this.canvasElement.getContext("2d");
    }

    async start(videoElement: HTMLVideoElement, onFrame: (b64: string) => void) {
        this.videoElement = videoElement;
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 360 },
                    facingMode: "user",
                },
            });
            this.videoElement.srcObject = this.stream;
            await this.videoElement.play();

            // Capture frames at ~0.5 FPS to save bandwidth but keep Gemini updated
            this.timer = window.setInterval(() => {
                this.captureFrame(onFrame);
            }, 2000);
        } catch (err) {
            console.error("Failed to start video stream:", err);
            throw err;
        }
    }

    private captureFrame(onFrame: (b64: string) => void) {
        if (!this.videoElement || !this.ctx || this.videoElement.videoWidth === 0) return;

        // Draw the current video frame to the canvas
        this.ctx.drawImage(
            this.videoElement,
            0,
            0,
            this.canvasElement.width,
            this.canvasElement.height
        );

        // Get JPEG base64 (quality 0.5 is a good balance for compression)
        const dataUrl = this.canvasElement.toDataURL("image/jpeg", 0.5);
        // Remove the "data:image/jpeg;base64," prefix
        const base64Data = dataUrl.split(",")[1];
        if (base64Data) {
            onFrame(base64Data);
        }
    }

    stop() {
        if (this.timer !== null) {
            window.clearInterval(this.timer);
            this.timer = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach((track) => track.stop());
            this.stream = null;
        }
        if (this.videoElement) {
            this.videoElement.srcObject = null;
        }
    }
}
