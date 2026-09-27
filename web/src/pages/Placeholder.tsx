/** Temporary page for sections built in a later phase. */
export default function Placeholder({ title }: { title: string }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      <p>This page is coming in the next build phase.</p>
    </div>
  )
}
