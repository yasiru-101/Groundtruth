import { Component, type ErrorInfo, type ReactNode } from "react"

import { ErrorState } from "./ErrorState"

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught error:", error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <ErrorState
            title="Unexpected error"
            error={this.state.error}
            retry={() => this.setState({ error: null })}
          />
        </div>
      )
    }
    return this.props.children
  }
}
