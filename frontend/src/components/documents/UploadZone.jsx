import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Upload, File } from 'lucide-react';
import { Button } from '@/ui/button';
import { cn } from '@/lib/utils';

export function UploadZone({ onUpload, disabled }) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (disabled) return;

    const files = Array.from(e.dataTransfer.files).filter(file => 
      file.name.endsWith('.pdf') || 
      file.name.endsWith('.txt') || 
      file.name.endsWith('.docx')
    );

    if (files.length > 0) {
      onUpload(files);
    } else {
      alert('Please upload PDF, TXT, or DOCX files only.');
    }
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      onUpload(files);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "border-2 border-dashed rounded-lg p-8 transition-smooth cursor-pointer",
        isDragging 
          ? "border-primary bg-primary/5" 
          : "border-border hover:border-primary/50 hover:bg-muted/50",
        disabled && "opacity-50 cursor-not-allowed"
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.docx"
        onChange={handleFileSelect}
        className="hidden"
        disabled={disabled}
      />

      <div className="flex flex-col items-center justify-center text-center space-y-4">
        <motion.div
          animate={isDragging ? { scale: 1.1 } : { scale: 1 }}
          className={cn(
            "w-16 h-16 rounded-full flex items-center justify-center",
            isDragging ? "bg-primary/20" : "bg-muted"
          )}
        >
          {isDragging ? (
            <File className="w-8 h-8 text-primary" />
          ) : (
            <Upload className="w-8 h-8 text-muted-foreground" />
          )}
        </motion.div>

        <div>
          <p className="text-sm font-medium text-foreground mb-1">
            {isDragging ? 'Drop files here' : 'Click or drag files to upload'}
          </p>
          <p className="text-xs text-muted-foreground">
            Supports PDF, TXT, and DOCX files
          </p>
        </div>

        <Button 
          variant="outline" 
          size="sm"
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation();
            handleClick();
          }}
        >
          Browse Files
        </Button>
      </div>
    </motion.div>
  );
}
