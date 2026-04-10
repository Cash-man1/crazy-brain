/** URL profilo Instagram (imposta su Render: VITE_INSTAGRAM_URL=https://instagram.com/tuo_profilo) */
export const INSTAGRAM_URL =
  (import.meta.env.VITE_INSTAGRAM_URL as string | undefined)?.trim() || ''
