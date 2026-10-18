export interface AssistantViewportBounds {
  top: number;
  left: number;
  width: number;
  height: number;
  keyboard: boolean;
}

export interface VisualViewportLike {
  width: number;
  height: number;
  offsetTop: number;
  offsetLeft: number;
}

/**
 * No WebView do Android o teclado encolhe o visual viewport, mas elementos `fixed` podem
 * continuar ancorados no layout viewport. O painel passa a usar a área visível real.
 */
export function panelBounds(
  viewport: VisualViewportLike | null,
  innerHeight: number,
  narrowScreen: boolean,
): AssistantViewportBounds | null {
  if (!viewport) return null;
  const keyboard = viewport.height < innerHeight - 120;
  if (!keyboard && !narrowScreen) return null;
  const margin = 8;
  return {
    top: viewport.offsetTop + margin,
    left: viewport.offsetLeft + margin,
    width: Math.max(200, viewport.width - margin * 2),
    height: Math.max(200, viewport.height - margin * 2),
    keyboard,
  };
}
