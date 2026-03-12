import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, FileText, Zap, Brain, TrendingUp, ShieldAlert, Scale } from 'lucide-react';
import { Card } from '@/ui/card';

export function ChatEmpty({ onQuestionClick, selectedDocs = [] }) {
  // Logic to determine "Smart Questions" based on file types
  const suggestions = useMemo(() => {
    // 1. Default Questions
    let questions = [
      { icon: FileText, text: "What are the key takeaways?" },
      { icon: Brain, text: "Summarize this document" },
    ];

    if (!selectedDocs || selectedDocs.length === 0) return questions;

    // 2. Detect Content Types
    const hasFinancials = selectedDocs.some(doc => 
      doc.toLowerCase().includes('finance') || 
      doc.toLowerCase().includes('report') || 
      doc.endsWith('.csv') || 
      doc.endsWith('.xlsx')
    );

    const hasContracts = selectedDocs.some(doc => 
      doc.toLowerCase().includes('agreement') || 
      doc.toLowerCase().includes('contract') || 
      doc.toLowerCase().includes('legal')
    );

    // 3. Customize
    if (hasFinancials) {
      questions = [
        { icon: TrendingUp, text: "What are the financial highlights?" },
        { icon: Zap, text: "Identify any revenue risks" },
        { icon: Brain, text: "Compare Q1 vs Q2 performance" },
      ];
    } else if (hasContracts) {
      questions = [
        { icon: Scale, text: "What are the termination clauses?" },
        { icon: ShieldAlert, text: "List the liabilities and indemnities" },
        { icon: FileText, text: "Summarize the key obligations" },
      ];
    } else {
        // Mix for general PDFs
        questions.push({ icon: Zap, text: "What actionable insights are here?" });
    }

    return questions.slice(0, 3); // Return top 3
  }, [selectedDocs]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col items-center justify-center h-full p-6 text-center"
    >
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
        className="w-20 h-20 rounded-full bg-gradient-to-br from-primary/80 to-secondary/80 flex items-center justify-center mb-6 shadow-lg shadow-primary/20"
      >
        <MessageSquare className="w-10 h-10 text-white" />
      </motion.div>

      <h2 className="text-2xl font-bold text-foreground mb-2">
        Ready to analyze
      </h2>

      <p className="text-sm text-muted-foreground max-w-md mb-8">
        {selectedDocs.length > 0
          ? `I've loaded ${selectedDocs.length} document${selectedDocs.length > 1 ? 's' : ''}. Select a topic below or type your own question.`
          : "Select documents from the sidebar to start."}
      </p>

      <div className="w-full max-w-lg space-y-3">
        {suggestions.map((example, index) => {
          const Icon = example.icon;
          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + index * 0.1 }}
            >
              <Card
                className="p-4 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-smooth group"
                onClick={() => onQuestionClick?.(example.text)}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-muted group-hover:bg-primary/20 flex items-center justify-center flex-shrink-0 transition-colors">
                    <Icon className="w-4 h-4 text-primary" />
                  </div>
                  <p className="text-sm text-foreground text-left font-medium">
                    {example.text}
                  </p>
                </div>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}