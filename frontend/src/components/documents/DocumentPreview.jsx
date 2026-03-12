import { AlertCircle, FileText } from 'lucide-react';
import { Card } from '@/ui/card';
import { Alert, AlertDescription } from '@/ui/alert';

export function DocumentPreview({ filename, url }) {
  if (!filename) {
    return (
      <Card className="p-6 flex items-center justify-center h-full">
        <div className="text-center text-muted-foreground">
          <FileText className="w-16 h-16 mx-auto mb-4 opacity-20" />
          <p>Select a document to preview</p>
        </div>
      </Card>
    );
  }

  const extension = filename.split('.').pop().toLowerCase();
  const isDocx = extension === 'docx' || extension === 'doc';

  if (isDocx) {
    return (
      <Card className="p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">
          Preview: {filename}
        </h3>
        <Alert variant="warning">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            <strong>DOCX Preview Not Supported</strong>
            <p className="mt-2 text-sm">
              Microsoft Word documents cannot be previewed in the browser. 
              The document has been processed and is available for search and chat.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Supported preview formats: PDF, TXT
            </p>
          </AlertDescription>
        </Alert>
        
        {/* Download option */}
        <div className="mt-4">
          <a
            href={url}
            download={filename}
            className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
          >
            <FileText className="w-4 h-4" />
            Download {filename}
          </a>
        </div>
      </Card>
    );
  }

  // PDF or TXT preview
  return (
    <Card className="p-6">
      <h3 className="text-lg font-semibold text-foreground mb-4">
        Preview: {filename}
      </h3>
      <div className="aspect-[3/4] bg-muted rounded-lg overflow-hidden">
        {extension === 'pdf' ? (
          <iframe
            src={url}
            className="w-full h-full"
            title={filename}
          />
        ) : extension === 'txt' ? (
          <iframe
            src={url}
            className="w-full h-full p-4"
            title={filename}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            Preview not available for this file type
          </div>
        )}
      </div>
    </Card>
  );
}
