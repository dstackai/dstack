import org.gradle.api.tasks.Exec

open class AwsTask : Exec() {
    override fun getGroup(): String {
        return "aws"
    }

    var stage: String? = null
        set(value) {
            field = value
            this.updateCommand()
        }

    var profile: String? = null
        set(value) {
            field = value
            this.updateCommand()
        }

    fun updateCommand() {
        val command = mutableListOf("aws", "s3", "sync", "build/", "s3://dstackai-website-${stage!!}", "--acl", "public-read")
        if (profile != null) {
            command += listOf("--profile", profile!!)
        }
        this.commandLine = command.toList()
    }
}