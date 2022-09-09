import org.gradle.api.tasks.Exec

open class ExecCommandTask : Exec() {
    var command: String = ""
        set(value) {
            this.commandLine = value.split(" ")
        }
}