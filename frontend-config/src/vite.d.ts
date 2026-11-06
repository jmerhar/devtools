/** The settings app() returns, to merge into an application's Vite configuration. */
export interface AppConfig {
  server: { proxy: Record<string, string> };
  build: { target: string[]; license: { fileName: string } };
}

/** The oldest browsers a build supports. */
export declare const BROWSERS: string[];
/** Where the dev server sends /api when VITE_API_TARGET is unset. */
export declare const API_TARGET: string;
/** The settings, with the API's address read from VITE_API_TARGET when it is set. */
export declare function app(options?: { apiTarget?: string }): AppConfig;
