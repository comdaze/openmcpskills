/**
 * Skill execution configuration types
 * Matches backend SkillExecution model
 */

export interface SkillExecution {
  /** Execution type: instruction (default) or code_interpreter */
  type: 'instruction' | 'code_interpreter'
  /** Runtime environment: python or javascript */
  runtime: string
  /** Entry script path (relative to scripts/ directory) */
  entrypoint?: string
  /** Execution timeout in seconds */
  timeout: number
  /** Network mode: sandbox (no network) or public */
  network: 'sandbox' | 'public'
  /** Dependencies to install */
  dependencies: string[]
}

export interface ExecutionResult {
  /** Execution status */
  status: 'success' | 'error' | 'timeout'
  /** Exit code */
  exit_code: number
  /** Standard output */
  stdout: string
  /** Standard error */
  stderr: string
  /** Execution duration in milliseconds */
  duration_ms: number
  /** Generated output files with download URLs */
  output_files?: OutputFile[]
}

export interface OutputFile {
  /** File name */
  filename: string
  /** S3 presigned download URL */
  download_url: string
  /** S3 URI */
  s3_uri?: string
  /** URL expiration time in seconds */
  expires_in?: number
}

/** Default execution configuration */
export const DEFAULT_EXECUTION: SkillExecution = {
  type: 'instruction',
  runtime: 'python',
  timeout: 300,
  network: 'sandbox',
  dependencies: [],
}
