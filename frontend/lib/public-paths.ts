/** Páginas que se abren sin sesión: el login y la política de privacidad (la pide Google). */
const PUBLIC_PATH = /^\/(es|pt)\/(login|privacy)\/?$/;

export const LOGIN_PATH = /^\/(es|pt)\/login\/?$/;

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATH.test(pathname);
}
