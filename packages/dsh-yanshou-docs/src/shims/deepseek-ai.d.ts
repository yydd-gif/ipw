/**
 * Minimal shims so this bundle can typecheck/build without installing
 * @deepseek-ai/* (those packages are provided by the host dsh at runtime,
 * and npm's graph is incomplete — dsh-type-meta 404).
 */

declare module '@deepseek-ai/cordis' {
  export interface Context {
    tools: {
      register(tool: unknown): void
    }
  }
}

declare module '@deepseek-ai/dsh-tools' {
  export function defineTool(def: {
    name: string
    description: string
    parameters: Record<string, unknown>
    output: {
      schema: { type: 'string' }
      render: (args: unknown, value: string) => Array<{ type: 'text'; text: string }>
    }
    execute: (args: Record<string, unknown>) => Promise<string> | string
  }): unknown
}

declare module '@deepseek-ai/schemastery' {
  interface Schema<T = unknown> {
    required(): Schema<T>
    default(value: T): Schema<T>
  }
  interface SchemaStatic {
    object(shape: Record<string, any>): Schema<any>
    string(): Schema<string>
    number(): Schema<number>
    boolean(): Schema<boolean>
    array(inner: Schema<any>): Schema<any>
  }
  const Schema: SchemaStatic
  export default Schema
}
