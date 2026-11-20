import type { Linter } from "eslint";

/** Components, and the modules that use runes outside a component. */
export declare const SVELTE_FILES: string[];

/** The Svelte configuration; place it after base(). */
export declare function svelte(files?: string[]): Linter.Config[];
