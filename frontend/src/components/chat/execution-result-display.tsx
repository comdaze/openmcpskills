import { Terminal, Clock, CheckCircle2, XCircle, AlertTriangle, Download, FileDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CopyButton } from './copy-button'
import type { ExecutionResult } from '@/types/skill'

interface ExecutionResultDisplayProps {
  result: ExecutionResult
}

export function ExecutionResultDisplay({ result }: ExecutionResultDisplayProps) {
  const getStatusIcon = () => {
    switch (result.status) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />
      case 'timeout':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
    }
  }

  const getStatusBadge = () => {
    const variants: Record<ExecutionResult['status'], 'default' | 'destructive' | 'secondary'> = {
      success: 'default',
      error: 'destructive',
      timeout: 'secondary',
    }
    return <Badge variant={variants[result.status]}>{result.status}</Badge>
  }

  return (
    <div className="mt-3 pt-3 border-t space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Terminal className="w-4 h-4" />
          Execution Result
        </div>
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          {getStatusBadge()}
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="w-3 h-3" />
            {result.duration_ms}ms
          </div>
          <Badge variant="outline" className="text-xs">
            exit: {result.exit_code}
          </Badge>
        </div>
      </div>

      {/* stdout */}
      {result.stdout && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-muted-foreground">stdout</span>
            <CopyButton text={result.stdout} size="sm" />
          </div>
          <pre className="text-xs bg-slate-900 text-green-400 p-3 rounded-lg overflow-x-auto max-h-60 font-mono">
            {result.stdout}
          </pre>
        </div>
      )}

      {/* stderr */}
      {result.stderr && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-red-500">stderr</span>
            <CopyButton text={result.stderr} size="sm" />
          </div>
          <pre className="text-xs bg-red-950 text-red-400 p-3 rounded-lg overflow-x-auto max-h-40 font-mono">
            {result.stderr}
          </pre>
        </div>
      )}

      {/* Output files */}
      {result.output_files && result.output_files.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FileDown className="w-4 h-4" />
            <span className="text-xs font-medium text-muted-foreground">Generated Files</span>
          </div>
          <div className="space-y-2">
            {result.output_files.map((file, idx) => (
              <a
                key={idx}
                href={file.download_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 p-2 rounded-lg border bg-card hover:bg-accent transition-colors group"
              >
                <Download className="w-4 h-4 text-primary group-hover:text-primary/80" />
                <span className="text-sm font-medium flex-1 truncate">{file.filename}</span>
                <Button variant="outline" size="sm" className="h-7 text-xs">
                  Download
                </Button>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* No output */}
      {!result.stdout && !result.stderr && (!result.output_files || result.output_files.length === 0) && (
        <div className="text-sm text-muted-foreground italic">
          No output produced
        </div>
      )}
    </div>
  )
}
