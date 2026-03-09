"use client";

import { useEffect, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "error";

interface VoiceOrbProps {
  state: OrbState;
  voiceLevel: number;
  onClick?: () => void;
  className?: string;
}

const STATE_HUES: Record<OrbState, number> = {
  idle: 0,
  listening: 160,
  thinking: 40,
  speaking: 280,
  error: 340,
};

const STATE_LABELS: Record<OrbState, string> = {
  idle: "Click to begin",
  listening: "Listening",
  thinking: "Searching sources",
  speaking: "Speaking",
  error: "Connection error",
};

const VERT = `
precision highp float;
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}`;

const FRAG = `
precision highp float;
uniform float iTime;
uniform vec3 iResolution;
uniform float hue;
uniform float hover;
uniform float rot;
uniform float hoverIntensity;
varying vec2 vUv;

vec3 rgb2yiq(vec3 c) {
  return vec3(
    dot(c, vec3(0.299,0.587,0.114)),
    dot(c, vec3(0.596,-0.274,-0.322)),
    dot(c, vec3(0.211,-0.523,0.312))
  );
}
vec3 yiq2rgb(vec3 c) {
  return vec3(
    c.x + 0.956*c.y + 0.621*c.z,
    c.x - 0.272*c.y - 0.647*c.z,
    c.x - 1.106*c.y + 1.703*c.z
  );
}
vec3 adjustHue(vec3 color, float hueDeg) {
  float hueRad = hueDeg * 3.14159265 / 180.0;
  vec3 yiq = rgb2yiq(color);
  float cosA = cos(hueRad), sinA = sin(hueRad);
  yiq.yz = vec2(yiq.y*cosA - yiq.z*sinA, yiq.y*sinA + yiq.z*cosA);
  return yiq2rgb(yiq);
}

vec3 hash33(vec3 p3) {
  p3 = fract(p3 * vec3(0.1031,0.11369,0.13787));
  p3 += dot(p3, p3.yxz + 19.19);
  return -1.0 + 2.0 * fract(vec3(p3.x+p3.y, p3.x+p3.z, p3.y+p3.z) * p3.zyx);
}
float snoise3(vec3 p) {
  const float K1 = 0.333333333, K2 = 0.166666667;
  vec3 i = floor(p + (p.x+p.y+p.z)*K1);
  vec3 d0 = p - (i - (i.x+i.y+i.z)*K2);
  vec3 e = step(vec3(0.0), d0 - d0.yzx);
  vec3 i1 = e*(1.0 - e.zxy), i2 = 1.0 - e.zxy*(1.0 - e);
  vec3 d1 = d0 - (i1 - K2), d2 = d0 - (i2 - K1), d3 = d0 - 0.5;
  vec4 h = max(0.6 - vec4(dot(d0,d0),dot(d1,d1),dot(d2,d2),dot(d3,d3)), 0.0);
  vec4 n = h*h*h*h * vec4(dot(d0,hash33(i)),dot(d1,hash33(i+i1)),dot(d2,hash33(i+i2)),dot(d3,hash33(i+1.0)));
  return dot(vec4(31.316), n);
}

vec4 extractAlpha(vec3 c) { float a = max(max(c.r,c.g),c.b); return vec4(c/(a+1e-5), a); }

const vec3 baseColor1 = vec3(0.612,0.263,0.996);
const vec3 baseColor2 = vec3(0.298,0.761,0.914);
const vec3 baseColor3 = vec3(0.063,0.078,0.600);
const float innerRadius = 0.6;
const float noiseScale = 0.65;

float light1(float i, float a, float d) { return i / (1.0 + d * a); }
float light2(float i, float a, float d) { return i / (1.0 + d * d * a); }

vec4 draw(vec2 uv) {
  vec3 c1 = adjustHue(baseColor1, hue), c2 = adjustHue(baseColor2, hue), c3 = adjustHue(baseColor3, hue);
  float ang = atan(uv.y, uv.x), len = length(uv), invLen = len > 0.0 ? 1.0/len : 0.0;
  float n0 = snoise3(vec3(uv*noiseScale, iTime*0.5))*0.5+0.5;
  float r0 = mix(mix(innerRadius,1.0,0.4), mix(innerRadius,1.0,0.6), n0);
  float d0 = distance(uv, (r0*invLen)*uv);
  float v0 = light1(1.0,10.0,d0) * smoothstep(r0*1.05, r0, len);
  float cl = cos(ang + iTime*2.0)*0.5+0.5;
  float a = iTime*-1.0;
  vec2 pos = vec2(cos(a),sin(a))*r0;
  float d = distance(uv, pos);
  float v1 = light2(1.5,5.0,d) * light1(1.0,50.0,d0);
  float v2 = smoothstep(1.0, mix(innerRadius,1.0,n0*0.5), len);
  float v3 = smoothstep(innerRadius, mix(innerRadius,1.0,0.5), len);
  vec3 col = clamp((mix(c3, mix(c1,c2,cl), v0) + v1) * v2 * v3, 0.0, 1.0);
  return extractAlpha(col);
}

void main() {
  vec2 center = iResolution.xy * 0.5;
  float size = min(iResolution.x, iResolution.y);
  vec2 uv = (vUv * iResolution.xy - center) / size * 2.0;
  float s = sin(rot), c = cos(rot);
  uv = vec2(c*uv.x - s*uv.y, s*uv.x + c*uv.y);
  uv.x += hover * hoverIntensity * 0.1 * sin(uv.y*10.0 + iTime);
  uv.y += hover * hoverIntensity * 0.1 * sin(uv.x*10.0 + iTime);
  vec4 col = draw(uv);
  gl_FragColor = vec4(col.rgb * col.a, col.a);
}`;

export function VoiceOrb({ state, voiceLevel, onClick, className }: VoiceOrbProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({ state, voiceLevel });
  const glRef = useRef<{
    renderer: any;
    program: any;
    mesh: any;
    gl: WebGLRenderingContext;
  } | null>(null);

  stateRef.current = { state, voiceLevel };

  const initGL = useCallback(async () => {
    const el = containerRef.current;
    if (!el || glRef.current) return;

    const OGL = await import("ogl");
    const { Renderer, Program, Mesh, Triangle, Vec3 } = OGL;

    try {
      const renderer = new Renderer({
        alpha: true,
        premultipliedAlpha: false,
        antialias: true,
        dpr: Math.min(window.devicePixelRatio || 1, 2),
      });
      const gl = renderer.gl;
      gl.clearColor(0, 0, 0, 0);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      el.appendChild(gl.canvas);

      const geometry = new Triangle(gl);
      const program = new Program(gl, {
        vertex: VERT,
        fragment: FRAG,
        uniforms: {
          iTime: { value: 0 },
          iResolution: { value: new Vec3(gl.canvas.width, gl.canvas.height, 1) },
          hue: { value: 0 },
          hover: { value: 0 },
          rot: { value: 0 },
          hoverIntensity: { value: 0 },
        },
      });
      const mesh = new Mesh(gl, { geometry, program });
      glRef.current = { renderer, program, mesh, gl };

      // Size
      const w = el.clientWidth;
      const h = el.clientHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      renderer.setSize(w * dpr, h * dpr);
      gl.canvas.style.width = w + "px";
      gl.canvas.style.height = h + "px";
      program.uniforms.iResolution.value.set(gl.canvas.width, gl.canvas.height, 1);

      // Animate
      let currentHue = 0;
      let currentVoice = 0;
      let currentRot = 0;
      let lastTime = 0;

      const loop = (t: number) => {
        if (!glRef.current) return;
        const dt = (t - lastTime) * 0.001;
        lastTime = t;

        const { state: s, voiceLevel: vl } = stateRef.current;
        const targetHue = STATE_HUES[s] || 0;
        currentHue += (targetHue - currentHue) * 0.05;
        currentVoice += (vl - currentVoice) * 0.12;

        const baseSpeed = s === "thinking" ? 0.8 : 0.2;
        currentRot += dt * (baseSpeed + currentVoice * 1.5);

        const p = program.uniforms;
        p.iTime.value = t * 0.001;
        p.hue.value = currentHue;
        p.rot.value = currentRot;
        p.hover.value = Math.min(currentVoice * 1.5 + (s === "thinking" ? 0.4 : 0), 1.0);
        p.hoverIntensity.value = Math.min(currentVoice * 0.6 + (s === "thinking" ? 0.3 : 0), 0.8);

        gl.clear(gl.COLOR_BUFFER_BIT);
        renderer.render({ scene: mesh });
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    } catch {
      // WebGL not available — show CSS fallback
      el.innerHTML = '<div class="w-full h-full rounded-full bg-gradient-to-br from-violet-600 to-cyan-600 animate-pulse" />';
    }
  }, []);

  useEffect(() => {
    initGL();
    return () => {
      if (glRef.current) {
        (glRef.current.gl.canvas as HTMLCanvasElement).remove();
        glRef.current = null;
      }
    };
  }, [initGL]);

  return (
    <div className={cn("flex flex-col items-center gap-3", className)}>
      <div className="relative">
        {/* Orbital rings */}
        <div
          className={cn(
            "absolute inset-[-14px] rounded-full border border-zinc-800/40 animate-pulse-ring",
            state === "listening" && "border-teal-500/20",
            state === "thinking" && "border-amber-500/20",
            state === "speaking" && "border-violet-500/20",
          )}
          style={{ animationDuration: "4s" }}
        />
        <div
          className={cn(
            "absolute inset-[-28px] rounded-full border border-dashed border-zinc-800/20",
            state === "listening" && "border-teal-500/10",
            state === "thinking" && "border-amber-500/10",
            state === "speaking" && "border-violet-500/10",
          )}
          style={{ animation: "spin 20s linear infinite reverse" }}
        />

        {/* Orb */}
        <div
          ref={containerRef}
          onClick={onClick}
          className="w-[140px] h-[140px] rounded-full overflow-hidden cursor-pointer transition-transform duration-300 hover:scale-[1.03] active:scale-95"
        />
      </div>

      {/* Label */}
      <span
        className={cn(
          "text-xs font-medium tracking-wide transition-colors duration-300",
          state === "idle" && "text-zinc-600",
          state === "listening" && "text-teal-400/70",
          state === "thinking" && "text-amber-400/70 animate-pulse",
          state === "speaking" && "text-violet-400/70",
          state === "error" && "text-red-400/70",
        )}
      >
        {STATE_LABELS[state]}
      </span>
    </div>
  );
}
