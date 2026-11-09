// Draws every game as a translucent dot on the GPU. Positions, sizes and
// colours are uploaded once; a pan or zoom only changes a few uniforms, so
// tens of thousands of dots stay smooth (PERF 3).

export interface DotData {
  /** Model coordinates, in draw order (later dots are drawn on top). */
  xs: Float32Array;
  ys: Float32Array;
  /** Radius multiplier per dot (see mapScale.dotScale). */
  scales: Float32Array;
  /** RGB 0–1 per dot, three values each. */
  colors: Float32Array;
}

export interface DotView {
  zoom: number;
  panX: number;
  panY: number;
  /** Base radius in CSS px; each dot is baseRadius × its scale. */
  baseRadius: number;
  width: number;
  height: number;
  dpr: number;
}

export const DOT_OPACITY = 0.55;
const MIN_RADIUS = 0.7; // smaller GPU points can vanish

const VERTEX_SHADER = `
attribute vec2 a_pos;
attribute float a_scale;
attribute vec3 a_color;
uniform vec2 u_size;
uniform vec2 u_pan;
uniform float u_zoom;
uniform float u_radius;
uniform float u_dpr;
uniform float u_maxPoint;
varying vec3 v_color;
varying float v_diameter;
void main() {
  vec2 screen = a_pos * u_zoom + u_pan;
  gl_Position = vec4(screen.x / u_size.x * 2.0 - 1.0, 1.0 - screen.y / u_size.y * 2.0, 0.0, 1.0);
  // One extra device pixel leaves room for the anti-aliased edge.
  v_diameter = min(max(u_radius * a_scale, ${MIN_RADIUS.toFixed(2)}) * 2.0 * u_dpr + 1.0, u_maxPoint);
  gl_PointSize = v_diameter;
  v_color = a_color;
}`;

const FRAGMENT_SHADER = `
precision mediump float;
uniform float u_alpha;
varying vec3 v_color;
varying float v_diameter;
void main() {
  // Device px from the centre; fades over the last pixel for a smooth edge.
  float distance = length(gl_PointCoord - 0.5) * v_diameter;
  float alpha = clamp(v_diameter * 0.5 - distance, 0.0, 1.0) * u_alpha;
  if (alpha <= 0.0) discard;
  gl_FragColor = vec4(v_color * alpha, alpha);
}`;

export interface DotLayer {
  draw(view: DotView): void;
  dispose(): void;
}

/** Returns null when WebGL is unavailable; the caller then draws dots in 2D. */
export function createDotLayer(canvas: HTMLCanvasElement, data: DotData): DotLayer | null {
  const gl = canvas.getContext('webgl', { antialias: false, premultipliedAlpha: true });
  if (!gl) return null;

  function compile(type: number, source: string) {
    const shader = gl!.createShader(type)!;
    gl!.shaderSource(shader, source);
    gl!.compileShader(shader);
    if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) {
      throw new Error(gl!.getShaderInfoLog(shader) ?? 'Shader compile failed');
    }
    return shader;
  }

  let program: WebGLProgram;
  try {
    program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX_SHADER));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT_SHADER));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  } catch {
    return null;
  }
  gl.useProgram(program);

  const count = data.xs.length;
  const positions = new Float32Array(count * 2);
  for (let i = 0; i < count; i++) {
    positions[2 * i] = data.xs[i];
    positions[2 * i + 1] = data.ys[i];
  }
  const buffers: WebGLBuffer[] = [];
  function attribute(name: string, values: Float32Array, size: number) {
    const buffer = gl!.createBuffer()!;
    buffers.push(buffer);
    gl!.bindBuffer(gl!.ARRAY_BUFFER, buffer);
    gl!.bufferData(gl!.ARRAY_BUFFER, values, gl!.STATIC_DRAW);
    const location = gl!.getAttribLocation(program, name);
    gl!.enableVertexAttribArray(location);
    gl!.vertexAttribPointer(location, size, gl!.FLOAT, false, 0, 0);
  }
  attribute('a_pos', positions, 2);
  attribute('a_scale', data.scales, 1);
  attribute('a_color', data.colors, 3);

  const uniform = (name: string) => gl.getUniformLocation(program, name);
  const u = {
    size: uniform('u_size'),
    pan: uniform('u_pan'),
    zoom: uniform('u_zoom'),
    radius: uniform('u_radius'),
    dpr: uniform('u_dpr'),
    maxPoint: uniform('u_maxPoint'),
    alpha: uniform('u_alpha'),
  };
  const pointRange = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE) as Float32Array;
  gl.uniform1f(u.maxPoint, pointRange[1]);
  gl.uniform1f(u.alpha, DOT_OPACITY);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

  return {
    draw(view) {
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(u.size, view.width, view.height);
      gl.uniform2f(u.pan, view.panX, view.panY);
      gl.uniform1f(u.zoom, view.zoom);
      gl.uniform1f(u.radius, view.baseRadius);
      gl.uniform1f(u.dpr, view.dpr);
      gl.drawArrays(gl.POINTS, 0, count);
    },
    dispose() {
      for (const buffer of buffers) gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    },
  };
}

/** Fallback for browsers without WebGL: the same dots drawn with Canvas 2D. */
export function drawDots2d(context: CanvasRenderingContext2D, data: DotData, view: DotView, hexColors: string[]) {
  context.globalAlpha = DOT_OPACITY;
  for (let i = 0; i < data.xs.length; i++) {
    const x = data.xs[i] * view.zoom + view.panX;
    const y = data.ys[i] * view.zoom + view.panY;
    const r = Math.max(view.baseRadius * data.scales[i], MIN_RADIUS);
    if (x < -r || y < -r || x > view.width + r || y > view.height + r) continue;
    context.fillStyle = hexColors[i];
    if (r < 1.5) {
      context.fillRect(x - r, y - r, 2 * r, 2 * r);
    } else {
      context.beginPath();
      context.arc(x, y, r, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.globalAlpha = 1;
}
