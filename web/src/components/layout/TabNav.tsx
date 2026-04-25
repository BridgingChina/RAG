import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Search, Upload } from "lucide-react"

interface TabNavProps {
  value: string
  onValueChange: (value: string) => void
}

export function TabNav({ value, onValueChange }: TabNavProps) {
  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto max-w-3xl px-6 py-4 flex items-center justify-between">
        <h1 className="font-serif text-xl font-semibold text-foreground">
          Bridge RAG
        </h1>
        <Tabs value={value} onValueChange={onValueChange}>
          <TabsList>
            <TabsTrigger value="ask" className="gap-1.5 cursor-pointer">
              <Search className="h-4 w-4" />
              问答
            </TabsTrigger>
            <TabsTrigger value="ingest" className="gap-1.5 cursor-pointer">
              <Upload className="h-4 w-4" />
              入库
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </header>
  )
}
